SELECT column1 AS ACCOUNT_ID,
       column2 AS ORGANIZATION_ID,
       column3 AS ACCOUNT_NAME,
       column4 AS SEGMENT,
       column5 AS ARR_USD,
       DATEADD(day, column6, CURRENT_DATE()) AS RENEWAL_DATE,
       column7 AS HEALTH
FROM VALUES
    ('ACC-1001', 'Es6d5vh20OoKzKwm8upOW-Q', 'Uniphore',      'Mid-market',  180000,  25, 'Green'),
    ('ACC-1002', 'EIv355L_XOrKU8mD10lyyeQ', 'Slack',         'Enterprise', 1200000,  40, 'Amber'),
    ('ACC-1003', 'E_j7i1alEOA6VKxhkV_yn5Q', 'Docker',        'Enterprise',  650000,  75, 'Green'),
    ('ACC-1004', 'EcizJxNywN4WY350qq0cr2Q', 'Cloudera',      'Enterprise',  420000,  20, 'Red'),
    ('ACC-1005', 'EoS12ey09M1SH2H43ucoMpQ', 'Okta',          'Enterprise',  900000, 150, 'Green'),
    ('ACC-1006', 'EIATbb7uwOhSYiGqLBPUD0w', 'Red Hat',       'Enterprise', 1500000,  60, 'Amber'),
    ('ACC-1007', 'EUSMLFV8NNIe22mVSEhJzCw', 'VMware',        'Enterprise', 2100000, 200, 'Red'),
    ('ACC-1008', 'EHyKUS1G-OwiHlrdVGmiUFA', 'Workday, Inc.', 'Enterprise',  780000,  85, 'Green')
