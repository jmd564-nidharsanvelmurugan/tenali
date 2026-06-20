prompts = {
        "IntroductionToJMAN":"""JMAN is a Data & Analytics Consultancy with 325 employees across London, Chennai, and New York. Our international team is a unique blend of consulting, data science and technology expertise. We specialise in working with private equity firms, and their portfolio companies across the investment lifecycle from diligence to exit. Over the last year, we have worked on 375+ projects with 100 portfolio companies across 51 funds. The experience we have on both sides of the deal in Diligence and at Exit, with some of the most sophisticated data adopters in private equity, gives us a good understanding of how businesses are evaluated, and what bidders are looking for from data.""",

        "BusinessContext": """Section heading: "Business Context :"
Generate a structured Business Context section in paragraphs, strictly do not add objectives, solutions or approach in the context: Take the context given by the user to inform generation of business context section""",

        "Overview": """Section heading: "Overview :"
Generate an abstract overview about what are all the services going to be provided (Refer question ans answers)
""",

        "Understanding": """Section heading: "Our Understanding of your needs :"
Generate a structured section that outlines the problem statement, proposed solution and its alignment with the client's needs, strictly take only the solution and do not add timelines, milestones, or the scope of work. Ensure the response is structured clearly, integrates the user’s description of the problem statement, proposed solution, and it’s alignment with clients needs with content from the best-in-class proposal templates. 
        """,

        "Objectives": """Section heading: "Objectives :"
Generate this section that outlines the proposed high level objectives of this project. Consider both user input and common objectives from the best-in-class proposal templates.  """,

        "Deliverables": """Section heading: "Deliverables :"
Generate this section that clearly outlines the deliverables and artifacts that we will provide to the client throughout this engagement. Prioritize question and answers here, but pull from best-in-class proposals where appropriate""",

        "Approach": """Section heading: "Approach :"
Generate this section that provides a high-level summary of the engagement, explaining how the approach is customized based on the complexity of the scope, existing data landscape, and business needs. Use all context provided by the user, enriching with language from the best-in-class proposal templates.  

Phase Breakdown: 
For each phase in the input, include: 
Phase Name & Duration (e.g., Phase 1: Design & Discovery, Duration: 6 weeks, Timeline: Week 1 to Week 6). 
Summary: A concise description of the phase’s purpose. 
Activities: A bullet-point list describing specific tasks. 
Do not create phases that are not mentioned in the input. 
Do not alter or extend the provided timelines. 
Ensure the Response Adheres to the Following Formatting Guidelines: 
Use bold for phase names and durations. 
Maintain clarity and readability with structured bullet points. 
Follow the exact phase breakdown and order from the input without deviation. 
This structured approach ensures alignment with the provided context while preventing the addition of unwanted phases. """,

        "Outcomes": """Section heading: "Outcomes :"
Generate this section that outlines the expected results and business impact of the engagement and deliverables, dynamically adapting based on project scope and industry context, and common outcomes from best-in-class proposals. """,

        "CaseStudies": """Section heading: "Relevant Case Studies :"
Generate the following text along with the section heading: [User to fill in Relevant Case Studes Text] """,

        "Commercials": """Section heading: "Commercials :"
Generate the following text along with the section heading: [User to fill in Commercials]"""

}

search_query = {
    "BusinessContext": "business cont"
}
AI_PROPOSAL_SYSTEM_PROMPT = """
You are an expert in generating professional consulting proposals, integrating structure, style, and content from example proposal documents.
YOUR TASK IS TO CREATE A PROPOSAL SECTION by following the structure, formatting, and style of the best in class proposal documents provided.
You are provided with set of questions and answers that TELLS WHO THE CLIENT IS, you will be generating PROPOSAL SECTION for this client.
Your target audience is C suite executives, private equity stakeholders, and experienced consultants. Your writing style should reflect this audience.
"""

DOCS_PROMPT = """
Use also the content from the documents as a reference to generate the proposal section.
"""
def get_section_prompts(section: str):
   # ['BusinessContext', 'Understanding', 'Objectives', 'Deliverables', 'Approach', 'Outcomes', 'CaseStudies', 'Commercials']
    # Hardcoded sections
    if (section == "IntroductionToJMAN"):
        return f"""
        Generate this below content as it is:

        *Introduction to JMAN :*
        {prompts[section]}
        """
    elif (section in ['CaseStudies', 'Commercials']):
        return prompts[section]

    return f"""
The required section to be generated is:
{prompts[section]}

GENERAL RULES TO FOLLOW:
Template Structure Adherence
 
- Analyze the BEST-IN-CLASS proposal's structure, sub-headings, formatting (bullet points, numbered lists) and STRICTLY generate the proposal content in a WELL-STRUCTURED MARKDOWN FORMAT, use h1 heading style for section headings, h2, h3 for appropriate sub-headings, ul for bullet points and ol for numbered lists.

- Before generating each response, give an empty line.

- After each response is generated, give an empty line before the next response.

Handling Information

- STRICTLY use the client name provided in the Q&A.

Content Integration Rules

- Missing Data: If no equivalent information exists in the Q&A, retain information from the set of best in class proposals.

- Conflicting Info: If Q&A contradicts the template, prioritize Q&A but maintain the template’s section structure.

Style & Tone

- Maintain the formal, third-person tone of the original template.

- Keep terminology consistent with what the user provides (e.x. if the user notes ‘Inorganic Growth’, do not write ‘Acquisition-based growth).

- The content and the narrative flow of the generated proposal should match the BEST-IN-CLASS proposal content.

Prohibited Actions

- Do NOT invent new sections that are not contained within the best-in-class proposals, unless noted by the user.
- Do NOT alter numbering/bulleting styles from the original template.
"""

