from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Atlas'
DB = ROOT / 'data' / 'atlas.sqlite'
AS_OF = '2026-10-07'
SEED = 42
PERSONAS = {
    'enterprise': {'name':'Meridian Dynamics','role':'CRO / CFO','period':'Q4 2026'},
    'university': {'name':'Alta Vista University','role':'President / VP Research','period':'FY27'},
    'developer': {'name':'Local development','role':'ENGINEER','period':'SYNTHETIC DATA'},
}
GOLDEN = [
    ('enterprise', 'forecast_quarter', "What's our projected Q4 revenue and profit?"),
    ('enterprise', 'deal_risk', 'Which five deals are most at risk this quarter, and why?'),
    ('enterprise', 'score_sites', 'Should we build a new sales center in Phoenix, Denver, or Albuquerque?'),
    ('enterprise', 'what_if', 'What happens to Q4 profit if our Commit stage win rate drops ten points?'),
    ('enterprise', 'region_vs_plan', 'Which region is furthest behind plan, and by how much?'),
    ('enterprise', 'hiring_plan', "How many reps do we need to hire to hit next year's target?"),
    ('enterprise', 'pipeline_coverage', 'How does our pipeline coverage compare to this time last year?'),
    ('enterprise', 'board_summary', 'Give me a thirty second board summary.'),
    ('university', 'grant_forecast', "Based on our grant pipeline, what's projected research funding for FY27?"),
    ('university', 'sponsor_concentration', "Which sponsors are we most dependent on, and what's the risk?"),
    ('university', 'score_sites', 'Where should we open our next research center?'),
    ('university', 'enrollment_forecast', "What's our projected fall enrollment yield?"),
]

UPGRADE_GOLDEN=[
    ('developer','developer_top','Write a SQL query for the top ten accounts by open pipeline, and run it.'),
    ('developer','developer_csv','Write a Python script that exports the Q4 forecast by region to CSV, then run it.'),
]
UPGRADE_GOLDEN += [
    ('enterprise','search_knowledge','What did the last QBR say about risk in our weakest region?'),
    ('enterprise','search_knowledge',"Summarize the board's concerns about margin."),
    ('enterprise','search_knowledge','Which accounts does our pricing policy flag for discount approval?'),
    ('university','search_knowledge','Which PIs have the strongest NIH track record?'),
    ('university','search_knowledge','What does the sponsor guidance say about cost sharing?'),
    ('university','search_knowledge','Summarize our enrollment strategy risks.'),
]
UPGRADE_GOLDEN += [
    ('developer','developer_explain','Explain how the Q4 forecast is calculated and show me the code.'),
    ('developer','developer_tests','Write unit tests for the site scoring function and run them.'),
    ('developer','developer_past','Find open deals whose close date has already passed, and show me the query.'),
    ('developer','developer_api','Build a REST endpoint that returns pipeline coverage by region, and test it.'),
    ('developer','developer_plot','Plot win rate by stage from the historical deals.'),
    ('developer','developer_connect','How fast is the model running right now, and how do I connect my own tools to it?'),
]
