truncate table "proposal_questions";
INSERT INTO "proposal_questions" (id, question, type, options, category)
VALUES 
(1, 'What is the name of the client?

Example Input: Any Hour Group, LLC', 'TEXT', NULL, 'GENERAL'),

(2, 'What is the business model?', 'DROPDOWN', 
    ARRAY['SaaS', 'Financial Services', 'Field Services', 'Professional Services', 'Other'], 
    'BUSINESS_OFFERING'),

(3, 'What solution does this project fall under?', 'DROPDOWN',
    ARRAY['Core Reporting', 'Due Diligence', 'Data Advisory', 'Value Creation', 'Exit Prep'],
    'SOLUTION'),

(4, 'What region does this client operate in?', 'RADIO',
    ARRAY['US', 'UK', 'Europe'],
    'REGION'),

(5, 'What is the project type?', 'RADIO',
    ARRAY['Design and Discovery', 'Build', 'Both'],
    'PROJECT_TYPE'),

(6, 'What is the commercial use case?', 'DROPDOWN',
    ARRAY['Revenue Bridge', 'Pipeline', 'Churn', 'Upsell/Cross-sell', 'Operational Reporting', 'Other'],
    'COMMERCIAL_USE_CASE'),

(7, 'What is the technical use case?', 'DROPDOWN',
    ARRAY['Data Platform', 'Gen AI', 'Data Science', 'Full-stack Development', 'Other'],
    'TECHNICAL_USE_CASE'),

(8, 'What is the client''s business model?', 'DROPDOWN',
    ARRAY['B2B', 'B2C', 'D2C', 'C2C'],
    'BUSINESS_MODEL'),

(9, 'Does the client have existing infrastructure (i.e. a data platform?)', 'RADIO',
    ARRAY['Yes', 'No'],
    'EXISTING_INFRA'),

(10, 'What is the client''s relationship to PE? ', 'DROPDOWN',
    ARRAY['PE Fund', 'PE Portco'],
    'PE_RELATIONSHIP');
