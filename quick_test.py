from backend.ai_matching import call_model_and_parse, skills_prompt

jd = """Role: Logistics Expert
Experience: 3–5 years

Responsibilities:
- Plan, manage, and monitor the movement of goods across domestic and international supply chains.
- Coordinate with vendors, transport providers, and warehouse teams to ensure on-time deliveries.
- Analyze logistics data to improve delivery times and reduce transportation costs.
- Manage inventory levels and optimize storage utilization.
- Ensure compliance with customs, safety, and quality standards.

Key Skills Required:
- Proficiency in SAP, MS Excel, and logistics management software.
- Knowledge of freight forwarding, warehouse operations, and supply chain optimization.
- Strong understanding of inventory control, transportation management, and vendor coordination.
- Excellent analytical and communication skills.
- Certification in supply chain or logistics (e.g., CSCP, CILT) is a plus.
"""
cv = "Worked 4 years on Python and SQL at ACME Corp, built dashboards."
prompt = skills_prompt.format(jd_text=jd, cv_text=cv)

result = call_model_and_parse(prompt, "skills", "skills")
print("=== PARSED RESULT ===")
print(result)
