# Reading Pages and Generating Research
## Flow
- We will have a python script that does the following
- It will using the notion API to read the Archives db `2dfbad37f86a8084ab59f42395094f3e` (the id for the db in notion) and gather all pages created with the “Kindling Research” flag check to true.
- It will then find the pages that don’t contain a Green Background Toggled Header 2 section called “🪵 ✨Kindling Results” and display the names and a link to each of these pages in a terminal UI so I can choose which pages to do research for
- For the page or pages I select:
    - Read the contents of the page title and note content
    - Run a prompt <Prompt below Named “Extraction Prompt”> to extract any questions I am want to find answers to in the content and generate a brief that can be used to find answer for the questions. Use an efficient model to execute this
        - If there are no questions in the prompt the add a new Toggle Header 2 section “🪵 ✨Kindling Results” with green background and note this along with the time page was processed and estimated cost
    - If there is a brief and questions then pass the brief to Open AI + web search + 5.2 thinking with a prompt <prompt below named "Research Prompt"> to do research on the brief and produce a brief report (details in the prompt)
    - Add a toggle header 2 “🪵 ✨Kindling Results” with green background and note this along with the time page was processed and estimated cost of research.
        - This brief should be added in this block
- After this process is completed provide deep links to the pages that were processed

**Prompts**

*Extraction Prompt*

```markdown
{Title of Page}
{Body of Page}

<Task>
Given the text above, extract the question or the questions the author mentioned in it. Make sure to extract any details from the text that will aid in providing as direct of an answer as possible. Write the questions as a paragraph in the first person
</Task>
```

*Research Prompt*

```markdown
{Paragraph}

<Task>
You are an automated research assistant. Given the brief above containing one or more questions, produce a single short “article” that the user can read in ~5 minutes that achieves the following goals:

	- Provide the best preliminary answer you can from public information.
	- If a definitive answer is too complex/uncertain, give a high-level but useful take and clearly indicate uncertainty.
	- Encourage further exploration with concrete next steps.
</Task>

<Tools>
- Use web research iteratively as needed: search, read, refine searches to resolve contradictions and find primary/authoritative sources.
- Stop when you reach diminishing returns (new sources are repetitive or not improving confidence).
- If the answer isn’t knowable from public sources, say so and move to “Open loops” + “Next rabbit holes”.
</Tools

<Constraints>
- Target total length: ~700–900 words (approximate).
- Write in clear, direct language suitable for a daily newsletter.
- Use citations/links only to support the narrative; do not output just links.
</Constraints>

<Output Format>
You MUST provide all sections below in this order.

## 1) Headline
- Write a punchy, answer-shaped headline.
- Do NOT simply repeat the question verbatim.

## 2) Prompted by
- Include the original question(s) that triggered the research.
- Use the literal question if short; otherwise paraphrase crisply.
- If multiple questions exist, choose one primary question and optionally append “(+N related)”.

## 3) TL;DR
- 4–6 decisive bullets.
- Bullet 1 should be the best direct answer or best current take.
- Include 1–2 key caveats if needed, but do not over-hedge.

## 4) What I found
**Objective:** Deliver the best preliminary answer in a way that updates the user’s understanding and helps them decide what to do next.
Requirements:
- Answer-first: state the most likely answer/explanation early (even if partial).
- Explain the “why”: include the minimal reasoning/mechanism that makes the answer make sense.
- Ground key claims in evidence; cite sources where relevant.
- Scope it: specify conditions/assumptions/boundaries where the answer applies.
- Surface major tradeoffs/competing views when relevant.
- Keep it digestible: typically 2–4 short paragraphs, but adapt structure to the question type.
- Avoid exhaustive background, literature-review style writing, or long tangents.
- Avoid excessive hedging; reserve most uncertainty details for “Open loops”.

### 5) Open loops
- 2–4 bullets.
- Capture the most important uncertainties, disagreements, missing data, or edge cases.
- Phrase as crisp open questions when possible.

### 6) Next rabbit holes
- 3–5 items.
- Each item must include at least one of:
  - a suggested follow-up query the user could search
  - the type of source to consult (primary spec, review paper, standard, official guidance, etc.)
  - a decision criterion / test / red flag to look for
- Make these actionable, not generic.

### 7) Recommended reads + More sources
- Recommended reads: Top 3 sources the user should click first.
- More sources: Up to 7 additional sources (max total sources = 10).
- Prefer primary sources and high-quality references.
- No giant bibliography.

</Output Format>

```

## Technical Details
- I've include API keys for Open AI and Anthropic for use when querying llms in the .env file
- I've also included an API key for notion as well in the .env file
- Use langchain/langraph for orchestrations
- Product a requirements.txt file with packages needed to run this
## Other Details
- Include a Readme with how to install and run the script
## Testing
Make sure to write some unit test to ensure the script functionality is working

id for test pages in the archive db that you can use to verify that you can access this part of the db and also can write to it. Why-don-t-PT-practices-follow-the-stretch-lab-model-30bbad37f86a804a9e31ec40c5549aae
id for test page: Thinking-machines-and-dune-30abad37f86a80b099e5d39db193e08b

