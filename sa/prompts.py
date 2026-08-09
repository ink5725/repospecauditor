"""Prompt templates for all pipeline stages.

Prompts follow the design described in the paper (Tables 1-3):
  Stage 1: specification extraction / differential validation / generalization
  Stage 2: constraint applicability judgment + concretization
  Stage 3: query generation / violation checking / report pruning
All prompts are written from scratch for this reproduction.
"""

# --------------------------------------------------------------------- #
# Stage 1 - Specification extraction (paper Table 1, left column)      #
# --------------------------------------------------------------------- #
EXTRACT_SYSTEM = """You are a security analysis expert. Given a security patch, summarize a transferable, patch-grounded specification that captures the root cause and fixing logic. The specification will be used to detect similar bugs.

The specification has two parts:
- "entity": a syntactically detailed, specific natural-language description of the detection target (e.g., "A call to function kzalloc").
- "constraint": a constraint that reflects the fixing intention behind the patch (e.g., "The return value must be checked for NULL before being used").

Requirements:
1. Ground every claim in the patch itself. Do not invent facts.
2. Keep only syntax-level details that identify the vulnerable code location (function names, macros, struct names).
3. The constraint must capture the condition that was violated in the pre-patch code and is enforced by the fix.
4. Do not mention transient variable names, labels, or unrelated control-flow details.
5. If the bug involves multiple entities (e.g., allocation + release), name the main entity in "entity" and describe the others inside "constraint"."""

EXTRACT_USER = """Return strictly a JSON object with keys "entity" and "constraint".

# Patch description
{commit_message}

# Patch code (diff with full function context)
{patch_content}"""

# --------------------------------------------------------------------- #
# Stage 1 - Differential validation (paper Table 1, middle column)     #
# --------------------------------------------------------------------- #
VALIDATE_SYSTEM = """You are a security analysis expert. Your task is to analyze the given code and determine if it violates a given security specification. You need to understand the security specification clearly, then examine the code for the potential violation.

- Answer "yes" if the code violates the specification (the required condition does not hold on some execution path).
- Answer "no" if the code satisfies the specification."""

VALIDATE_USER = """Return strictly a JSON object with keys "decision" ("yes"/"no") and "reason".

# Specification
Entity: {entity}
Constraint: {constraint}

# Code under analysis
{code}"""

# --------------------------------------------------------------------- #
# Stage 1 - Generalization (paper Table 1, right column)               #
# --------------------------------------------------------------------- #
GENERALIZE_SYSTEM = """You are a program analysis expert. Given a concrete specification, your task is to generalize it into a more abstract and semantically meaningful form. Generalize the concrete code entities appearing in the entity and constraint, and describe the key bug-relevant behaviors they represent. The generalized description will be used to identify semantically similar entities.

Guidelines:
- Describe the underlying *behavior* (e.g., "allocating memory that must be explicitly released", "acquiring a reference that must be released", "copying data from user space") instead of specific function names.
- The generalized entity must describe the class of vulnerable behaviors, not a specific identifier.
- The generalized constraint must be the semantic requirement corresponding to that behavior.
- Keep the generalized entity SHORT (one sentence, under 25 words): it will be used as a semantic search query against documentation.
- Do not include patch-specific syntax (function names, variable names, file names)."""

GENERALIZE_USER = """Return strictly a JSON object with keys "generalized_entity" and "generalized_constraint".

# Concrete specification
Entity: {entity}
Constraint: {constraint}

# Original patch (for grounding)
{patch_content}"""

# --------------------------------------------------------------------- #
# Stage 2 - New specification generation (paper Table 2)               #
# --------------------------------------------------------------------- #
GENERATE_SYSTEM = """You are an experienced security researcher. Given a generalized specification consisting of an entity (the applicable behavior) and a constraint (the required constraint), determine whether a given code entity requires this constraint. Analyze the entity's implementation to see if its behavior matches the generalized behavior, examine its usage context, and decide whether callers must follow the constraint to avoid bugs.

Steps:
1. Read the generalized behavior and constraint.
2. Read the candidate entity's description, implementation (function definition) and usage examples.
3. Decide whether the candidate entity actually performs the vulnerable behavior described by the generalized entity.
4. If yes, decide whether the constraint applies to callers of this entity (it may not apply if the entity itself handles the requirement internally, e.g. managed/auto-release variants).
5. If the constraint applies, specialize the generalized constraint into a concrete, entity-specific constraint tailored to this entity's API.

Important: the constraint must be falsifiable for bug detection -- a caller of the entity either obeys it or not."""

GENERATE_USER = """Return strictly a JSON object with keys:
- "judgment": "yes" or "no" (whether this entity requires the constraint)
- "reason": brief justification
- "evidence": code evidence from the implementation or usages
- "concretized_specification": either null, or an object with keys "entity" (a syntactically detailed description of the detection target in code that uses this entity) and "constraint" (the concrete constraint the code should follow)

# Generalized specification
Generalized entity: {generalized_entity}
Generalized constraint: {generalized_constraint}

# Seed specification (concrete example from the original patch)
Seed entity: {seed_entity}
Seed constraint: {seed_constraint}

# Candidate entity documentation
{entity_description}

# Candidate entity implementation
{entity_source}

# Candidate entity usage examples
{entity_usages}"""

# --------------------------------------------------------------------- #
# Stage 3 - AST query generation (paper Table 3, left column)          #
# --------------------------------------------------------------------- #
QUERY_SYSTEM = """You are an expert in code analysis. Given the description of a target code location (the entity of a specification), extract the executable code-search intent:
- target_type: one of ["function_call", "function_definition", "struct_usage", "macro_call", "unknown"]
- identifier: the primary syntactic identifier (function / struct / macro name) that should be searched
- aliases: other identifiers mentioned that may also appear in code
This intent is executed against a C code index. Be conservative: only name identifiers that actually appear in source code."""

QUERY_USER = """Return strictly a JSON object with keys "target_type", "identifier", "aliases".

# Entity description
{entity_description}"""

# --------------------------------------------------------------------- #
# Stage 3 - Violation checking (paper Table 3, middle column)          #
# --------------------------------------------------------------------- #
VIOLATION_SYSTEM = """You are a security expert skilled in bug auditing. Given a function and a specification, determine whether the function violates the specified constraint and leads to a bug. Analyze involved variable usage and data flows, including aliases and escaped values. Check all execution paths and semantically equivalent code forms."""

VIOLATION_USER = """Return strictly a JSON object with keys "decision" ("yes"/"no") and "explanation".

# Specification
Entity: {entity}
Constraint: {constraint}

# Function code
{func_code}"""

# --------------------------------------------------------------------- #
# Stage 3 - Report pruning (paper Table 3, right column)               #
# --------------------------------------------------------------------- #
PRUNE_SYSTEM = """You are a senior bug analysis expert. Given a specification and a code snippet that appears to violate it, determine whether the snippet leads to a real bug. You may request extra context when the available evidence is insufficient.

Context requests use this form (one JSON object):
{"type": "more_context", "requests": [{"request_type": "source_code" | "usage_code", "entity_name": "<name>"}]}

- "source_code": the definition/implementation of the entity.
- "usage_code": code where the entity is used (e.g., its callers).

When you have enough evidence, give the final decision:
{"type": "final_decision", "decision": "yes"/"no", "explanation": "..."}"""

PRUNE_USER = """Analyze the potential violation below. Respond with EITHER a more_context request (only when evidence is insufficient) OR a final_decision.

# Specification
Entity: {entity}
Constraint: {constraint}

# Function that may violate the specification
{func_code}

# Extra context already supplied (if any)
{prev_context}"""
