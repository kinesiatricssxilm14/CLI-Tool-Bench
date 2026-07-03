# Detailed Analysis of "Zero-File Generation" Cases

During our evaluation of CLI-focused LLM agents, we observed that a notable proportion of trajectories resulted in zero valid code files being generated, despite consuming tokens and execution time. 

This phenomenon is particularly prevalent in the **OpenHands** framework. In this document, we delve into the execution trajectories of these failed cases to understand the underlying behavioral patterns of different models.

## Pattern 1: Unauthorized Workspace Relocation ("Hallucinated Directories")

Some highly capable models (such as MiniMax-2.5) successfully generate the entire project code but fail the evaluation because they fundamentally misunderstand the sandbox environment's constraints.

**Example Case: `drpaneas/parsepico` (MiniMax-2.5 under Mini-SWE-Agent)**

**Behavioral Trajectory:**
Instead of operating in the intended mounted repository directory (e.g., `/workspace` or the current working directory provided by the framework), the agent immediately issues absolute path commands to reconstruct its own isolated environment.

1. **Step 1:** The agent forces the creation of a new root directory:
   `{"command": "mkdir -p /workspace && cd /workspace && ls -la"}`
2. **Step 2:** It initializes the Go module in this *new* isolated path:
   `{"command": "cd /workspace && go mod init parsepico"}`
3. **Step 3-N:** It successfully writes hundreds of lines of code (`main.go`) and compiles it using `go build`.

**Why it fails:**
Because the agent performed all actions in a self-created `/workspace` path rather than the framework's strictly monitored target directory, the evaluation scripts collect zero modifications when examining the target repository. This reveals a critical lack of "embodied awareness" regarding relative paths and sandbox constraints.

## Pattern 2: Premature Termination (Safety Filters and Strict Output Formats)

Other models, particularly Claude-Sonnet-4.6, exhibit a "fail-fast" behavior, leading to zero files generated with minimal token consumption (often just 1 step).

**Example Case: `umputun/unfuck-ai-comments` (Claude-Sonnet-4.6 under OpenHands)**

**Behavioral Trajectory:**
1. **Step 1:** The agent receives the initial prompt containing the repository name (`unfuck-ai-comments`).
2. **Step 2:** The agent immediately terminates the session, consuming only 118 tokens and issuing zero bash commands.

**Why it fails:**
This abrupt termination is largely attributed to two factors:
1. **Overly Sensitive Safety Alignment:** The presence of profanity in the repository name or specific keywords in the prompt triggers the model's safety filters, causing it to refuse the task entirely (e.g., responding with "I cannot fulfill this request" instead of a valid JSON tool call).
2. **Strict Tool-Call Constraints:** OpenHands requires strict JSON-formatted tool calls. If a model starts its response with natural language apologies or clarifications instead of executing commands, the framework may fail to parse the action and prematurely abort the trajectory.

## Conclusion

These "zero-file" cases highlight that evaluating CLI agents goes beyond measuring raw coding capability. It requires assessing an agent's ability to strictly follow environment boundaries, adapt to specific directory structures, and navigate the delicate balance between safety alignment and task execution.
