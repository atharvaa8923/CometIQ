"""CometIQ skill taxonomy and career role families.

Each skill: (name, category, aliases, is_emerging).
Aliases are matched case-insensitively on word boundaries; an alias prefixed with
"=" is matched case-sensitively (for short tokens like "R" or "Go"), and one prefixed
with "re:" is a raw regular expression (for context, e.g. "communication" but not
"data communications").
"""

CATEGORIES = [
    "Analytics & Data", "AI & Machine Learning", "Software & Cloud", "Cybersecurity",
    "Finance", "Accounting", "Information Systems", "Marketing",
    "Operations & Supply Chain", "Management & Strategy", "Healthcare", "Professional Skills",
]

SKILLS: list[tuple[str, str, list[str], bool]] = [
    # ── Analytics & Data ──────────────────────────────────────────────────────
    ("SQL", "Analytics & Data", ["sql", "structured query language", "t-sql", "pl/sql", "mysql", "postgresql", "sql server"], False),
    ("Python", "Analytics & Data", ["python", "jupyter"], False),
    ("R", "Analytics & Data", ["=R", "r programming", "rstudio", "tidyverse"], False),
    ("Excel", "Analytics & Data", ["excel", "spreadsheet", "spreadsheets", "vlookup", "pivot table", "pivot tables"], False),
    ("Advanced Excel Modeling", "Analytics & Data", ["excel modeling", "excel solver", "vba", "power query"], False),
    ("Tableau", "Analytics & Data", ["tableau"], False),
    ("Power BI", "Analytics & Data", ["power bi", "powerbi", "dax"], False),
    ("Data Visualization", "Analytics & Data", ["data visualization", "visualisation", "dashboards", "dashboard", "visual analytics", "storytelling with data"], False),
    ("Statistics", "Analytics & Data", ["statistics", "statistical analysis", "statistical methods", "hypothesis testing", "probability", "inferential statistics"], False),
    ("Regression Analysis", "Analytics & Data", ["regression", "linear regression", "logistic regression"], False),
    ("Forecasting", "Analytics & Data", ["forecasting", "time series", "time-series", "demand forecasting", "arima"], False),
    ("Data Mining", "Analytics & Data", ["data mining", "clustering", "classification trees", "association rules"], False),
    ("Data Cleaning", "Analytics & Data", ["data cleaning", "data wrangling", "data preparation", "data quality", "data preprocessing"], False),
    ("Data Warehousing", "Analytics & Data", ["data warehouse", "data warehousing", "dimensional modeling", "star schema", "snowflake"], False),
    ("ETL / Data Pipelines", "Analytics & Data", ["etl", "elt", "data pipeline", "data pipelines", "data integration", "airflow", "dbt"], False),
    ("Big Data (Spark/Hadoop)", "Analytics & Data", ["apache spark", "pyspark", "spark sql", "hadoop", "big data", "databricks", "apache hive"], False),
    ("Database Design", "Analytics & Data", ["database design", "relational database", "relational databases", "data modeling", "normalization", "erd", "database management"], False),
    ("NoSQL Databases", "Analytics & Data", ["nosql", "mongodb", "cassandra", "dynamodb"], False),
    ("Optimization", "Analytics & Data", ["optimization", "linear programming", "integer programming", "mathematical programming", "operations research"], False),
    ("Simulation", "Analytics & Data", ["simulation", "monte carlo", "discrete event simulation"], False),
    ("A/B Testing & Experimentation", "Analytics & Data", ["a/b testing", "ab testing", "experimentation", "experimental design", "causal inference"], False),
    ("Business Intelligence", "Analytics & Data", ["business intelligence", "bi tools", "looker", "qlik"], False),
    ("Predictive Analytics", "Analytics & Data", ["predictive analytics", "predictive modeling", "predictive models"], False),
    ("Prescriptive Analytics", "Analytics & Data", ["prescriptive analytics", "decision analytics", "decision analysis", "decision models"], False),
    ("Econometrics", "Analytics & Data", ["econometrics", "panel data"], False),

    # ── AI & Machine Learning ─────────────────────────────────────────────────
    ("Machine Learning", "AI & Machine Learning", ["machine learning", "ml models", "supervised learning", "unsupervised learning", "scikit-learn", "sklearn", "random forest", "xgboost"], False),
    ("Deep Learning", "AI & Machine Learning", ["deep learning", "neural network", "neural networks", "cnn", "rnn", "pytorch", "tensorflow", "keras"], False),
    ("Natural Language Processing", "AI & Machine Learning", ["natural language processing", "nlp", "text mining", "text analytics", "sentiment analysis"], False),
    ("Generative AI & LLMs", "AI & Machine Learning", ["generative ai", "genai", "large language model", "large language models", "llm", "llms", "chatgpt", "gpt", "claude", "foundation models"], True),
    ("Prompt Engineering", "AI & Machine Learning", ["prompt engineering", "prompt design"], True),
    ("Retrieval-Augmented Generation", "AI & Machine Learning", ["retrieval-augmented generation", "retrieval augmented generation", "rag", "vector database", "vector databases", "embeddings"], True),
    ("AI Agents", "AI & Machine Learning", ["ai agents", "agentic", "agentic ai", "autonomous agents", "langchain", "multi-agent"], True),
    ("MLOps", "AI & Machine Learning", ["mlops", "model deployment", "model monitoring", "mlflow"], True),
    ("Computer Vision", "AI & Machine Learning", ["computer vision", "image recognition", "object detection"], False),
    ("Responsible AI & AI Ethics", "AI & Machine Learning", ["responsible ai", "ai ethics", "algorithmic bias", "ai governance", "explainable ai", "model fairness"], True),
    ("Reinforcement Learning", "AI & Machine Learning", ["reinforcement learning"], False),

    # ── Software & Cloud ──────────────────────────────────────────────────────
    ("Java", "Software & Cloud", ["java", "spring boot"], False),
    ("JavaScript", "Software & Cloud", ["javascript", "typescript", "node.js", "nodejs", "react.js", "reactjs", "angular"], False),
    ("Web Development", "Software & Cloud", ["web development", "html", "css", "web applications", "front-end", "frontend", "full stack", "full-stack"], False),
    ("APIs & Integration", "Software & Cloud", ["api", "apis", "rest api", "restful", "web services", "microservices", "system integration"], False),
    ("Git & Version Control", "Software & Cloud", ["git", "github", "version control", "gitlab"], False),
    ("Cloud Computing", "Software & Cloud", ["cloud computing", "cloud platforms", "cloud services", "cloud"], False),
    ("AWS", "Software & Cloud", ["aws", "amazon web services", "ec2", "s3", "sagemaker"], False),
    ("Microsoft Azure", "Software & Cloud", ["azure"], False),
    ("Google Cloud", "Software & Cloud", ["google cloud", "gcp", "bigquery"], False),
    ("DevOps & CI/CD", "Software & Cloud", ["devops", "ci/cd", "continuous integration", "continuous delivery", "jenkins"], False),
    ("Containers (Docker/Kubernetes)", "Software & Cloud", ["docker", "kubernetes", "containers", "containerization"], False),
    ("Software Development Lifecycle", "Software & Cloud", ["sdlc", "software development life cycle", "software development lifecycle", "software engineering"], False),
    ("Object-Oriented Programming", "Software & Cloud", ["object-oriented", "object oriented", "oop"], False),
    ("Low-Code / Automation", "Software & Cloud", ["low-code", "low code", "no-code", "rpa", "robotic process automation", "power automate", "uipath"], True),
    ("Blockchain", "Software & Cloud", ["blockchain", "distributed ledger", "smart contracts", "cryptocurrency", "crypto assets"], False),

    # ── Cybersecurity ─────────────────────────────────────────────────────────
    ("Cybersecurity Fundamentals", "Cybersecurity", ["cybersecurity", "cyber security", "information security", "infosec", "security controls"], False),
    ("Network Security", "Cybersecurity", ["network security", "firewall", "firewalls", "intrusion detection", "ids/ips", "vpn"], False),
    ("Risk Management Frameworks (NIST/ISO)", "Cybersecurity", ["nist", "iso 27001", "cobit", "security frameworks", "risk management framework"], False),
    ("Identity & Access Management", "Cybersecurity", ["identity and access management", "iam", "access control", "zero trust", "authentication"], False),
    ("Incident Response", "Cybersecurity", ["incident response", "siem", "security operations center", "threat detection", "splunk", "security operations"], False),
    ("Cloud Security", "Cybersecurity", ["cloud security"], True),
    ("Cryptography", "Cybersecurity", ["cryptography", "encryption"], False),
    ("Privacy & Data Protection", "Cybersecurity", ["privacy", "data protection", "gdpr", "hipaa compliance", "ccpa"], False),

    # ── Finance ───────────────────────────────────────────────────────────────
    ("Financial Modeling", "Finance", ["financial modeling", "financial model", "financial models", "three-statement model", "dcf model"], False),
    ("Valuation", "Finance", ["valuation", "discounted cash flow", "dcf", "business valuation", "equity valuation"], False),
    ("Corporate Finance", "Finance", ["corporate finance", "capital budgeting", "cost of capital", "capital structure", "wacc"], False),
    ("Investment Analysis", "Finance", ["investment analysis", "investments", "equity research", "securities analysis", "asset management"], False),
    ("Portfolio Management", "Finance", ["portfolio management", "portfolio theory", "asset allocation", "portfolio optimization"], False),
    ("Derivatives", "Finance", ["derivatives", "options pricing", "futures contracts", "swaps", "option pricing", "black-scholes"], False),
    ("Fixed Income", "Finance", ["fixed income", "bonds", "bond valuation", "interest rate risk"], False),
    ("Financial Risk Management", "Finance", ["financial risk", "risk management", "value at risk", "credit risk", "market risk"], False),
    ("Fintech", "Finance", ["fintech", "financial technology", "digital payments", "payments", "digital banking", "insurtech"], True),
    ("Real Estate Finance", "Finance", ["real estate", "commercial real estate", "reit", "reits"], False),
    ("Banking", "Finance", ["banking", "commercial banking", "investment banking", "lending"], False),
    ("Bloomberg Terminal", "Finance", ["bloomberg"], False),
    ("ESG & Sustainable Finance", "Finance", ["esg", "sustainable finance", "sustainability reporting", "climate risk"], True),

    # ── Accounting ────────────────────────────────────────────────────────────
    ("Financial Accounting", "Accounting", ["financial accounting", "financial statements", "financial reporting", "balance sheet", "income statement"], False),
    ("GAAP / IFRS", "Accounting", ["gaap", "ifrs", "accounting standards", "fasb", "asc 606"], False),
    ("Managerial & Cost Accounting", "Accounting", ["managerial accounting", "cost accounting", "budgeting", "variance analysis", "activity-based costing"], False),
    ("Auditing", "Accounting", ["auditing", "audit", "external audit", "internal audit", "assurance", "audit procedures"], False),
    ("Taxation", "Accounting", ["taxation", "tax", "tax planning", "tax compliance", "tax research"], False),
    ("Internal Controls & SOX", "Accounting", ["internal controls", "internal control", "sox", "sarbanes-oxley", "coso"], False),
    ("Governance, Risk & Compliance", "Accounting", ["grc", "governance, risk", "compliance", "regulatory compliance"], False),
    ("IT Audit", "Accounting", ["it audit", "information systems audit", "cisa", "it general controls", "itgc"], False),
    ("Forensic Accounting", "Accounting", ["forensic accounting", "fraud examination", "fraud detection"], False),
    ("Audit Analytics", "Accounting", ["audit analytics", "audit data analytics", "idea software", "acl analytics", "alteryx"], True),

    # ── Information Systems ───────────────────────────────────────────────────
    ("ERP Systems (SAP/Oracle)", "Information Systems", ["erp", "enterprise resource planning", "sap", "oracle erp", "s/4hana", "netsuite"], False),
    ("CRM Systems (Salesforce)", "Information Systems", ["crm", "salesforce", "customer relationship management", "hubspot", "dynamics 365"], False),
    ("Business Process Management", "Information Systems", ["business process", "process modeling", "bpmn", "process mining", "process improvement"], False),
    ("Systems Analysis & Design", "Information Systems", ["systems analysis", "systems design", "requirements gathering", "requirements analysis", "use cases", "user stories"], False),
    ("IT Project Management", "Information Systems", ["project management", "pmp", "project planning", "gantt", "ms project"], False),
    ("Agile & Scrum", "Information Systems", ["agile", "scrum", "kanban", "sprint", "jira"], False),
    ("IT Strategy & Governance", "Information Systems", ["it strategy", "it governance", "itil", "enterprise architecture", "digital transformation"], False),
    ("Product Management", "Information Systems", ["product management", "product manager", "product roadmap", "product strategy", "product lifecycle"], False),
    ("UX & Design Thinking", "Information Systems", ["user experience", "ux", "design thinking", "user research", "prototyping", "figma"], False),
    ("Health Information Systems", "Information Systems", ["health information", "electronic health records", "ehr", "emr", "epic systems", "health it", "hl7", "fhir"], False),

    # ── Marketing ─────────────────────────────────────────────────────────────
    ("Digital Marketing", "Marketing", ["digital marketing", "online marketing", "email marketing", "paid media", "ppc"], False),
    ("SEO / SEM", "Marketing", ["seo", "search engine optimization", "sem", "search engine marketing", "google ads"], False),
    ("Social Media Marketing", "Marketing", ["social media", "social media marketing", "influencer marketing"], False),
    ("Marketing Analytics", "Marketing", ["marketing analytics", "google analytics", "web analytics", "attribution", "marketing mix"], False),
    ("Market Research", "Marketing", ["market research", "marketing research", "survey design", "conjoint", "focus groups", "consumer research"], False),
    ("Brand Management", "Marketing", ["brand management", "branding", "brand strategy", "brand equity"], False),
    ("Consumer Behavior", "Marketing", ["consumer behavior", "buyer behavior", "customer insights"], False),
    ("Customer Analytics", "Marketing", ["customer analytics", "customer segmentation", "segmentation", "customer lifetime value", "churn"], False),
    ("Pricing Strategy", "Marketing", ["pricing", "pricing strategy", "revenue management"], False),
    ("Content Marketing", "Marketing", ["content marketing", "content strategy", "copywriting"], False),
    ("Sales & Business Development", "Marketing", ["sales", "business development", "account management", "b2b sales"], False),
    ("Marketing Automation", "Marketing", ["marketing automation", "marketo", "pardot", "mailchimp"], True),

    # ── Operations & Supply Chain ─────────────────────────────────────────────
    ("Supply Chain Management", "Operations & Supply Chain", ["supply chain", "supply chain management", "scm", "value chain"], False),
    ("Logistics & Transportation", "Operations & Supply Chain", ["logistics", "transportation", "distribution network", "distribution centers", "warehousing", "freight"], False),
    ("Procurement & Sourcing", "Operations & Supply Chain", ["procurement", "sourcing", "purchasing", "supplier management", "vendor management", "strategic sourcing"], False),
    ("Inventory Management", "Operations & Supply Chain", ["inventory", "inventory management", "inventory control", "safety stock", "eoq"], False),
    ("Lean & Six Sigma", "Operations & Supply Chain", ["lean manufacturing", "lean principles", "lean management", "lean operations", "six sigma", "lean six sigma", "dmaic", "kaizen", "continuous improvement"], False),
    ("Quality Management", "Operations & Supply Chain", ["quality management", "quality control", "total quality", "tqm", "statistical process control", "spc"], False),
    ("Operations Management", "Operations & Supply Chain", ["operations management", "production planning", "capacity planning", "scheduling", "operations strategy"], False),
    ("Demand Planning / S&OP", "Operations & Supply Chain", ["demand planning", "s&op", "sales and operations planning", "mrp"], False),
    ("Supply Chain Analytics", "Operations & Supply Chain", ["supply chain analytics", "network design", "supply chain optimization"], True),
    ("Systems Engineering", "Operations & Supply Chain", ["systems engineering", "systems thinking", "model-based systems engineering", "mbse", "requirements engineering"], False),
    ("Energy Markets", "Operations & Supply Chain", ["energy industry", "energy management", "energy sector", "oil and gas", "renewable energy", "power markets", "energy markets"], False),

    # ── Management & Strategy ─────────────────────────────────────────────────
    ("Strategic Management", "Management & Strategy", ["strategic management", "strategy", "competitive strategy", "competitive advantage", "strategic planning"], False),
    ("Leadership", "Management & Strategy", ["leadership", "leading teams", "people management"], False),
    ("Organizational Behavior", "Management & Strategy", ["organizational behavior", "organizational behaviour", "motivation", "team dynamics"], False),
    ("Change Management", "Management & Strategy", ["change management", "organizational change"], False),
    ("Entrepreneurship", "Management & Strategy", ["entrepreneurship", "startup", "startups", "new venture", "venture capital", "business plan"], False),
    ("Innovation Management", "Management & Strategy", ["innovation", "innovation management", "corporate innovation", "r&d management"], False),
    ("International Business", "Management & Strategy", ["international business", "global business", "global strategy", "cross-cultural", "international management"], False),
    ("Negotiation", "Management & Strategy", ["negotiation", "negotiations", "conflict resolution"], False),
    ("Business Ethics", "Management & Strategy", ["ethics", "business ethics", "ethical", "corporate social responsibility", "csr"], False),
    ("Business Law", "Management & Strategy", ["business law", "contracts", "legal environment", "employment law"], False),
    ("Human Resource Management", "Management & Strategy", ["human resource", "human resources", "hr management", "talent management", "recruiting", "compensation"], False),
    ("Economics", "Management & Strategy", ["economics", "microeconomics", "macroeconomics", "managerial economics"], False),
    ("Management Consulting", "Management & Strategy", ["consulting", "management consulting", "case interviews", "client engagement"], False),

    # ── Healthcare ────────────────────────────────────────────────────────────
    ("Healthcare Management", "Healthcare", ["healthcare management", "health care management", "healthcare administration", "hospital management", "healthcare operations"], False),
    ("Healthcare Policy & Regulation", "Healthcare", ["health policy", "healthcare policy", "hipaa", "cms regulations", "healthcare regulation"], False),
    ("Healthcare Analytics", "Healthcare", ["healthcare analytics", "health analytics", "clinical data", "population health"], True),

    # ── Professional Skills ───────────────────────────────────────────────────
    ("Communication", "Professional Skills", [r"re:(?<!data )(?<!network )(?<!wireless )(?<!digital )communication(?!s? (?:network|protocol|system)s?)", "communication skills", "presentation", "presentations", "public speaking", "written communication"], False),
    ("Teamwork & Collaboration", "Professional Skills", ["teamwork", "collaboration", "cross-functional", "team projects", "team project"], False),
    ("Critical Thinking & Problem Solving", "Professional Skills", ["critical thinking", "problem solving", "problem-solving", "analytical thinking"], False),
    ("Stakeholder Management", "Professional Skills", ["stakeholder", "stakeholders", "stakeholder management", "executive communication"], False),
    ("Business Writing & Reporting", "Professional Skills", ["business writing", "report writing", "technical writing", "documentation"], False),
]

# Career role families: title keywords (for classifying job titles) and the
# skill profile we assume when a posting has no description.
ROLE_FAMILIES: dict[str, dict] = {
    "Data Analyst": {
        "keywords": ["data analyst", "analytics analyst", "reporting analyst", "bi analyst", "business intelligence analyst", "insights analyst"],
        "skills": ["SQL", "Excel", "Tableau", "Power BI", "Python", "Statistics", "Data Visualization", "Data Cleaning", "Communication"],
    },
    "Data Scientist": {
        "keywords": ["data scientist", "decision scientist", "quantitative analyst", "applied scientist"],
        "skills": ["Python", "Machine Learning", "Statistics", "SQL", "Regression Analysis", "Predictive Analytics", "Deep Learning", "A/B Testing & Experimentation", "Generative AI & LLMs"],
    },
    "ML / AI Engineer": {
        "keywords": ["machine learning engineer", "ml engineer", "ai engineer", "mlops", "llm engineer", "genai engineer"],
        "skills": ["Python", "Machine Learning", "Deep Learning", "MLOps", "Generative AI & LLMs", "Retrieval-Augmented Generation", "AWS", "Containers (Docker/Kubernetes)", "APIs & Integration"],
    },
    "Business Analyst": {
        "keywords": ["business analyst", "business systems analyst", "systems analyst", "functional analyst", "process analyst"],
        "skills": ["Systems Analysis & Design", "SQL", "Excel", "Business Process Management", "Agile & Scrum", "Stakeholder Management", "Data Visualization", "Communication"],
    },
    "Financial Analyst": {
        "keywords": ["financial analyst", "finance analyst", "fp&a", "investment analyst", "equity research", "credit analyst", "valuation analyst", "treasury analyst"],
        "skills": ["Financial Modeling", "Excel", "Valuation", "Corporate Finance", "Forecasting", "Financial Accounting", "Power BI", "Communication"],
    },
    "Fintech / Quant Analyst": {
        "keywords": ["fintech", "quant", "quantitative", "risk analyst", "payments analyst"],
        "skills": ["Python", "Fintech", "Financial Risk Management", "Machine Learning", "SQL", "Derivatives", "Statistics", "Blockchain"],
    },
    "Accountant / Auditor": {
        "keywords": ["accountant", "auditor", "audit associate", "tax associate", "staff accountant", "assurance associate", "controller", "accounting"],
        "skills": ["Financial Accounting", "GAAP / IFRS", "Auditing", "Internal Controls & SOX", "Excel", "Taxation", "Audit Analytics", "ERP Systems (SAP/Oracle)"],
    },
    "IT / Cybersecurity Analyst": {
        "keywords": ["security analyst", "cybersecurity", "cyber security", "information security", "grc analyst", "it auditor", "soc analyst", "risk and compliance"],
        "skills": ["Cybersecurity Fundamentals", "Risk Management Frameworks (NIST/ISO)", "Network Security", "Incident Response", "Identity & Access Management", "Cloud Security", "IT Audit", "Governance, Risk & Compliance"],
    },
    "Product Manager": {
        "keywords": ["product manager", "product owner", "associate product manager", "technical product manager"],
        "skills": ["Product Management", "Agile & Scrum", "UX & Design Thinking", "Stakeholder Management", "SQL", "A/B Testing & Experimentation", "Communication", "Generative AI & LLMs"],
    },
    "Marketing Analyst": {
        "keywords": ["marketing analyst", "digital marketing", "marketing manager", "growth", "brand manager", "seo", "marketing specialist"],
        "skills": ["Marketing Analytics", "Digital Marketing", "SEO / SEM", "Customer Analytics", "SQL", "Excel", "A/B Testing & Experimentation", "Market Research"],
    },
    "Supply Chain Analyst": {
        "keywords": ["supply chain", "logistics", "procurement", "buyer", "demand planner", "operations analyst", "inventory analyst", "sourcing"],
        "skills": ["Supply Chain Management", "Excel", "SQL", "Demand Planning / S&OP", "Inventory Management", "ERP Systems (SAP/Oracle)", "Logistics & Transportation", "Optimization"],
    },
    "Management Consultant": {
        "keywords": ["consultant", "consulting", "strategy analyst", "advisory"],
        "skills": ["Management Consulting", "Strategic Management", "Excel", "Communication", "Stakeholder Management", "Critical Thinking & Problem Solving", "Data Visualization", "Change Management"],
    },
    "Healthcare Administrator": {
        "keywords": ["healthcare", "health care", "hospital", "clinical", "health system", "patient"],
        "skills": ["Healthcare Management", "Healthcare Policy & Regulation", "Health Information Systems", "Healthcare Analytics", "Lean & Six Sigma", "Leadership", "Excel", "Quality Management"],
    },
    "Software Engineer": {
        "keywords": ["software engineer", "software developer", "developer", "full stack", "backend engineer", "frontend engineer", "data engineer"],
        "skills": ["Python", "Java", "JavaScript", "SQL", "Git & Version Control", "APIs & Integration", "Cloud Computing", "DevOps & CI/CD"],
    },
}


def classify_role(title: str) -> str | None:
    t = (title or "").lower()
    best, best_len = None, 0
    for family, spec in ROLE_FAMILIES.items():
        for kw in spec["keywords"]:
            if kw in t and len(kw) > best_len:
                best, best_len = family, len(kw)
    return best
