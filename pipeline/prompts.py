"""Frozen coarse H/I stigma prompt, aligned with the supplied V4.4 attribution scheme.

Prompt instructions are scientific inputs; their wording is preserved.
"""

def construct_prompt_simple(post_data, context_chain, target_comment):
    """Format the supplied high-recall coarse prompt (I: stigma; H: no stigma)."""
    post_title = post_data.get("title", "N/A")
    post_body = (post_data.get("selftext") or "")
    post_author = post_data.get("author_fullname", None)
    if not post_body.strip():
        post_body = "[No text content]"

    formatted_chain = []
    if not context_chain:
        chain_text = "[No previous context, this is a top-level comment]"
    else:
        for idx, comm in enumerate(context_chain):
            if comm.get("name") == target_comment.get("name"):
                continue
            uid = comm.get("author_fullname", "unknown")
            body = (comm.get("body") or "[deleted]").replace("\n", " ")
            formatted_chain.append(f"{idx + 1}.[User {uid}]: {body}")
        chain_text = (
            "\n".join(formatted_chain)
            if formatted_chain
            else "[No previous context, this is a top-level comment]"
        )

    target_uid = target_comment.get("author_fullname", "unknown")
    target_body = target_comment.get("body", "")

    prompt = f"""# Task
You are a high-recall mental illness stigma detector. Read the social media post, previous comments, and TARGET COMMENT, then decide whether the TARGET COMMENT itself expresses or clearly endorses ANY stigma toward a person or group associated with mental illness.

Label I = stigma is expressed or clearly endorsed.
Label H = no stigma is expressed or endorsed.

# What counts as stigma?
Stigma includes ANY of the following attitudes or actions:

- Blaming people for their mental illness or symptoms, treating the condition as a choice, excuse, weakness, laziness, or personal failure
- Avoiding, rejecting, excluding, or discouraging ordinary relationships with them because of mental illness
- Expressing anger, hostility, disgust, contempt, or a direct pathologizing attack toward them
- Withholding or ending support because helping them is considered futile or not worthwhile
- Showing no concern, dismissing, minimizing, trivializing, humiliating, or joking about their suffering
- Saying that they need, should, or must receive medication, treatment, hospitalization, institutionalization, or confinement
- Portraying them as dangerous, violent, frightening, unpredictable, or especially likely to engage in suicide or self-harm

The mental-health target may be another person, a group, or the commenter themself. Mental-health relevance includes mental illness, clear mental-health symptoms, suicidal or self-harming conditions, explicit addiction or alcoholism, personality disorders, and explicit diagnostic or pathologizing mental-health labels.

# Decision Rules
1. Judge the stance of the TARGET COMMENT. Use the Post and Comment Chain only to resolve its referent, meaning, and stance. Stigma elsewhere in the context is not enough.

2. A short affirmative reply such as "yes", "exactly", or "agreed" inherits stigma when it clearly endorses a stigmatizing previous comment. Quoting, reporting, questioning, criticizing, or rejecting stigma without endorsing it is H.

3. The mental-health referent may be supplied by an unambiguous antecedent in the Post or Comment Chain; the TARGET COMMENT does not need to repeat the diagnosis.

4. Explicit disorder or pathologizing labels may establish mental-health relevance. A generic insult such as "crazy", "unstable", or "not right in the head" does not establish it by itself.

5. Under this annotation scheme, direct statements that someone "needs", "should", or "must" receive therapy, medication, hospitalization, or other treatment count as I even when explicit force is not stated. Genuinely optional suggestions such as "may help", "consider talking to someone", or "I hope they get help" are H unless another stigmatizing attitude is present.

6. Supportive, neutral, factual, recovery-oriented, or self-disclosing comments are H when they do not contain stigma. A boundary based only on concrete abuse, violence, exploitation, or other specific conduct is H unless the TARGET COMMENT attributes the problem to mental illness.

7. Recall is more important than precision. After applying the stance and mental-health relevance rules above, choose I if a stigmatizing interpretation is reasonably supported. Do not choose I merely because mental illness or negative behavior appears somewhere in the context.

# Input

## Post
Title: {post_title}
Content: {post_body}

## Comment Chain (chronological)
{chain_text}

## TARGET COMMENT
User ID: {target_uid}
Comment: "{target_body}"

# Output Instruction
Return ONLY valid RFC 8259 JSON without Markdown fences:

{{
  "label": "<choose one from [H/I]>",
  "reasoning": "<One concise sentence identifying the decisive evidence or explaining why no stigma is expressed>",
  "user_id": "{target_uid}"
}}
"""
    return prompt.strip()
