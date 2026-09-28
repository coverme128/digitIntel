# Opportunity Taxonomy

## V1 Families

### EARNINGS_REVISION
来源：
- 8-K Item 2.02
- 10-Q / 10-K
- Exhibit 99.x
- official IR

关注：
- revenue
- EPS
- gross margin
- operating margin
- FCF
- guidance
- backlog / RPO / bookings（公司适用时）

### GUIDANCE_CHANGE
检测：
- raised
- lowered
- initiated
- withdrawn
- narrowed / widened

禁止只依靠语言关键词，必须绑定旧值、新值、期间。

### CAPITAL_RETURN
事件：
- repurchase authorization
- accelerated repurchase
- dividend change

核心：
- authorization / market cap
- execution credibility
- balance-sheet capacity

### INSIDER_OPEN_MARKET_BUY
来源：
- Form 4

仅将真正 open-market purchase 进入核心机会规则。
排除：
- option exercise
- grant
- tax withholding
- gift
- administrative transfer

### ACTIVIST_OWNERSHIP
来源：
- 13D / amendments
- 13G 作为 ownership context

关注：
- ownership %
- filer
- Item 4 purpose
- governance / sale / capital allocation language

### MATERIAL_CORPORATE_EVENT
例如：
- material agreement
- asset sale
- restructuring
- CEO/CFO change
- debt refinancing
- impairment
- material customer/contract when officially disclosed

### FINANCING_DILUTION
例如：
- secondary
- shelf activation
- convert issuance
- ATM program

核心：
- potential dilution %
- proceeds use
- liquidity runway context

### M&A_SPECIAL
V1 只做：
- deal detection
- terms extraction
- spread calculation
- key dates
不做：
- 自研 closing probability
- 自动 merger arb allocation
