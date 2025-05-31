from dotenv import load_dotenv
from langchain.prompts import PromptTemplate
from langchain.chat_models import init_chat_model
from typing_extensions import TypedDict
from typing import Literal
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

load_dotenv()

# global variables
llm = None
parser = None
reply_parser = None
workflow = None

# state for our AI agent


class State(TypedDict):
    application: str
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    leave_type: Literal["MEDICAL", "CASUAL"]
    start_date: str
    end_date: str
    remaining_leaves: int
    number_of_leaves: int
    which: str
    reply: str


# Structured output for model
class LeaveData(BaseModel):
    leave_type: str = Field(
        description="The type of leave classified into MEDICAL or CASUAL")
    start_date: str = Field(description="Starting date of leave")
    end_date: str = Field(description="End date of leave")
    number_of_leaves: int = Field(description="Number of leaves asked")


# Structured output for model response
class SystemResponse(BaseModel):
    reply: str = Field("Reply back to the user about leave application status")


def initialize_agent():
    print("Initializing the AI agent....")
    global llm, parser, reply_parser, workflow
    try:
        llm = init_chat_model(model="gemini-2.0-flash",
                              model_provider="google_genai")
        parser = PydanticOutputParser(pydantic_object=LeaveData)
        reply_parser = PydanticOutputParser(pydantic_object=SystemResponse)

        graph = StateGraph(state_schema=State)
        graph.add_node("analyze_leave_llm_node", analyze_leave_llm_node)
        graph.add_node("check_balance_leaves_node", check_balance_leaves_node)
        graph.add_node("reject_leave_node", reject_leave_node)
        graph.add_node("approve_leave_node", approve_leave_node)
        graph.add_node("human_feedback_leave_node", human_feedback_leave_node)
        graph.add_node("process_leave_node", process_leave_node)
        graph.add_edge(START, "analyze_leave_llm_node")
        graph.add_edge("analyze_leave_llm_node", "check_balance_leaves_node")
        graph.add_conditional_edges(
            "check_balance_leaves_node", conditional_edge_leave_balance)
        graph.add_conditional_edges(
            "process_leave_node", conditional_edge_process_leave)

        graph.add_edge("human_feedback_leave_node", END)
        graph.add_edge("reject_leave_node", END)
        graph.add_edge("approve_leave_node", END)

        workflow = graph.compile()
        print("Initializing the AI agent done....")

    except Exception as e:
        print(e)
        print("Something went wrong in init agent!!!")

    return


# function to call to invoke the agent
def run_agent(application: str):
    try:
        results = workflow.invoke({"application": application})
        print(results)
        return {
            "status": results["status"],
            "leave_type": results["leave_type"],
            "number_of_leaves": results["number_of_leaves"],
            "remaining_leaves": results["remaining_leaves"],
            "reply": results["reply"]
        }
    except Exception as e:
        return {"message": "Something went wrong", "original_message": e}


# ------ agent workflow -------


def analyze_leave_llm_node(state: State) -> State:
    prompt = PromptTemplate(
        template="Analyze the leave application and classify it into MEDICAL or CASUAL and also extract the start date and end date of leave in ISO format along with number of leave days.\n{format_instructions}\n{query}",
        input_variables=["query"],
        partial_variables={
            "format_instructions": parser.get_format_instructions()}

    )
    chain = prompt | llm | parser
    parsed_output = chain.invoke({"query": state["application"]})
    print(parsed_output)
    # parsed_output = parser.invoke(output)
    print(parsed_output)
    return {"leave_type": parsed_output.leave_type, "number_of_leaves": parsed_output.number_of_leaves}


def generate_reply(state: State) -> State:
    print("state in generate_reply", state)
    prompt = PromptTemplate(
        template="Based on this leave application and the status provided, generate a reply to send back to the applicant.\n{format_instructions}\n{query}\nstatus{status}",
        input_variables=["query", "tatus"],
        partial_variables={
            "format_instructions": reply_parser.get_format_instructions()}

    )
    chain = prompt | llm | reply_parser
    parsed_output = chain.invoke(
        {"query": state["application"], "status": state["status"]})
    # print(parsed_output)
    # parsed_output = parser.invoke(output)
    print(parsed_output)
    return {"reply": parsed_output.reply}


def check_balance_leaves_node(state: State) -> State:
    remaining_leaves = 10  # this will come from database
    if remaining_leaves - state['number_of_leaves'] >= 0:
        # proceed further
        return {"which": "process_leave_node", "status": "PENDING", "remaining_leaves": remaining_leaves}
    else:
        return {"which": "reject_leave_node", "status": "PENDING", "remaining_leaves": remaining_leaves}


def reject_leave_node(state: State) -> State:
    print("Leave rejected-- email the user")
    print(state)
    status = "REJECTED"
    state["status"] = status
    response = generate_reply(state)

    return {"status": status, "reply": response["reply"]}


def approve_leave_node(state: State) -> State:
    print("Approving leave --- send email to user")
    print(state)
    response = generate_reply(state)
    return {"status": "APPROVED", "reply": response["reply"]}


def human_feedback_leave_node(state: State) -> State:
    print("Taking feedback from human")
    response = generate_reply(state)

    return {"status": "PENDING", "reply": response["reply"]}


def process_leave_node(state: State) -> State:
    print("Processing leave further ---")
    if state["leave_type"] == "MEDICAL":
        if state["number_of_leaves"] == 1:
            return {"which": "approve_leave_node"}
        else:
            return {"which": "human_feedback_leave_node"}
    if state["leave_type"] == "CASUAL":
        return {"which": "human_feedback_leave_node"}


def conditional_edge_leave_balance(state: State) -> Literal["reject_leave_node", "process_leave_node"]:
    # Fill in arbitrary logic here that uses the state
    # to determine the next node
    return state["which"]


def conditional_edge_process_leave(state: State) -> Literal["approve_leave_node", "human_feedback_leave_node"]:
    return state["which"]
