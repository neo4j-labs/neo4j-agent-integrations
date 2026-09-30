TABLES (
    accounts AS ${customer_accounts}
      PRIMARY KEY (ACCOUNT_ID)
      COMMENT = 'Our customer accounts'
  )
  FACTS (
    accounts.arr_usd AS ARR_USD COMMENT = 'Annual recurring revenue in USD'
  )
  DIMENSIONS (
    accounts.account_id AS ACCOUNT_ID COMMENT = 'Account ID in the CRM',
    accounts.organization_id AS ORGANIZATION_ID COMMENT = 'The company''s organization ID',
    accounts.account_name AS ACCOUNT_NAME COMMENT = 'Company name',
    accounts.segment AS SEGMENT,
    accounts.renewal_date AS RENEWAL_DATE COMMENT = 'Next contract renewal',
    accounts.health AS HEALTH COMMENT = 'Account health: Green, Amber or Red'
  )
  METRICS (
    accounts.total_arr AS SUM(accounts.arr_usd) COMMENT = 'Total annual recurring revenue in USD'
  )
