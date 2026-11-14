"""Demo students (fictional) and an employer posting for CometMatch."""

DEMO_STUDENT_RESUME = """Jordan Rivera — MS Business Analytics & AI candidate, UT Dallas
SKILLS: SQL (PostgreSQL), Excel (pivot tables, VLOOKUP), Tableau dashboards, R, statistics, regression, data cleaning.
EXPERIENCE: Analytics Intern, Prairie Retail (Summer 2026) — built Tableau dashboards for weekly sales KPIs; wrote SQL queries
to reconcile inventory; presented findings to store managers. Team project: churn analysis in R with logistic regression.
INTERESTS: machine learning, generative AI."""

STUDENTS = [
    {"name": "Priya Shah", "email": "priya.shah@cometiq.app", "program": "Business Analytics and Artificial Intelligence", "conc": "Data Science",
     "goal": "Data Scientist", "headline": "ML-focused analytics grad student",
     "courses": ["BUAN 6312", "BUAN 6320", "BUAN 6359", "BUAN 6341", "BUAN 6383"],
     "resume": "Python (pandas, scikit-learn), machine learning, deep learning with PyTorch, SQL, statistics, A/B testing, data visualization in Tableau. Built an LLM-powered review summarizer using prompt engineering and RAG. Strong communication and teamwork."},
    {"name": "Marcus Johnson", "email": "marcus.johnson@cometiq.app", "program": "Business Analytics and Artificial Intelligence", "conc": "Data Engineering",
     "goal": "Software Engineer", "headline": "Data engineer in training",
     "courses": ["BUAN 6320", "BUAN 6346", "MIS 6309"],
     "resume": "SQL, Python, ETL data pipelines with Airflow and dbt, Snowflake data warehouse, Spark/Databricks, AWS (S3, EC2), Docker, Git and GitHub, CI/CD. Agile Scrum team experience."},
    {"name": "Elena Garcia", "email": "elena.garcia@cometiq.app", "program": "Master of Science in Finance", "conc": None,
     "goal": "Financial Analyst", "headline": "Aspiring FP&A analyst",
     "courses": [], "resume": "Financial modeling in Excel, valuation (DCF), corporate finance, financial statements, forecasting, Power BI dashboards, Bloomberg terminal. Presented investment pitch to faculty panel."},
    {"name": "Wei Chen", "email": "wei.chen@cometiq.app", "program": "Information Technology and Management", "conc": None,
     "goal": "Business Analyst", "headline": "Business systems analyst",
     "courses": [], "resume": "Requirements gathering, user stories, business process modeling (BPMN), SQL, Agile/Scrum with Jira, SAP ERP, stakeholder management, Power BI, documentation."},
    {"name": "Aisha Okafor", "email": "aisha.okafor@cometiq.app", "program": "Business Analytics and Artificial Intelligence", "conc": "Marketing Analytics",
     "goal": "Marketing Analyst", "headline": "Marketing analytics & growth",
     "courses": ["BUAN 6312", "BUAN 6320"],
     "resume": "Google Analytics, SQL, Excel, A/B testing, customer segmentation, marketing analytics, SEO, Tableau, survey design for market research, communication."},
]

EMPLOYER_JOB = {
    "title": "Data Analyst — New Grad",
    "location": "Richardson, TX",
    "employment_type": "Full-time",
    "description": ("Join Lone Star Analytics to turn client data into decisions.\n\nRequired qualifications:\n- SQL and relational databases\n"
                    "- Tableau or Power BI dashboards\n- Python for data analysis\n- Statistics and regression\n- Clear communication with stakeholders\n\n"
                    "Preferred qualifications:\n- Experience with generative AI tools\n- A/B testing\n- Data cleaning at scale"),
}
