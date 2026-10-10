# AGENTS.md

## Project
This repository is for 《還沒想到》科技新聞整理工具.

The goal is not to build a generic news scraper.
The goal is to help Ray collect technology news, explain technical context, and turn weekly topics into Podcast material.

## Ray's content preference
Ray is an engineer and Podcast host, not a financial analyst.

Prioritize:
1. New technologies, products, tools, platforms, architectures, or engineering workflows.
2. Engineering challenges: reliability, permissions, security, deployment, testing, performance, cost, maintainability, compatibility.
3. Practical use cases: where the technology can be applied.
4. Technical limitations: what is still hard, uncertain, manual, or not solved.
5. Possible solutions or industry direction.
6. Hacker News / Reddit / engineering community discussion when available.
7. Podcast angles that can explain the topic to non-engineers.

De-prioritize:
- stock price
- gross margin
- revenue details
- earnings call analysis
- investment conclusions
- financial speculation

Only mention financial data when it directly supports product adoption, technical demand, supply chain change, or engineering relevance.

## Editor Report requirements
The editor report must help Ray understand what the news is about.

Do not only say why a story was selected.
Explain the story.

Each selected news item should include:

### 1. 先講人話：這篇新聞在講什麼？
Use Traditional Chinese.
Explain the event clearly in 5–8 sentences.
Answer:
- Who is involved?
- What happened?
- What product, technology, company, market, or workflow is involved?
- What is the concrete claim?
- What can be understood from public information?

### 2. 背景補充：工程小白需要先懂什麼？
Use [Background] for general technical background.
Explain terms and concepts for non-experts.
Examples:
- What is Omniverse?
- What is simulation?
- What is rendering?
- What is an API?
- What is a test dataset?
- What does it mean to isolate evaluations from the internet?
- Why do AI agents need permission controls and audit logs?

### 3. 工程師應該注意什麼？
Use [Analysis].
Explain the engineering problem:
- What workflow does this affect?
- What may fail?
- What needs testing?
- What is hard to automate?
- Does it involve security, permissions, reliability, deployment, maintenance, performance, or cost?

### 4. 目前可能的解法或業界方向
Use [Reported] for source-supported claims.
Use [Analysis] for engineering inference.
If there is no clear solution, say so directly.

### 5. 網路上的人可能會怎麼看？
If Hacker News / Reddit discussion is available, summarize it.
If no direct discussion exists, list three engineering questions people might ask.
Do not claim these are actual community opinions unless sourced.

### 6. Ray 的 Podcast 切入角度
Write 2–3 sentences in Ray's voice.
Tone: friendly, curious, clear, not financial-news style.

### 7. 仍需查證的地方
Put uncertainty here, not at the beginning.
Be specific:
- official docs needed
- technical docs needed
- benchmark needed
- product policy needed
- API example needed
- deployment case needed
- HN / Reddit discussion needed

Avoid repeating generic phrases like:
- 資料不足
- 來源未提供
- 待人工補充

Instead, say exactly what is missing and why it matters.

## Source and copyright rules
Do not bypass paywalls.
Do not scrape full articles.
Do not output full article text.
Do not use paywalled content unless Ray provides it.
Do not treat metadata as confirmed facts.
Do not treat social media comments as facts.

Allowed:
- title
- URL
- source
- published date
- public metadata
- public summary
- RSS
- official blog / press release
- GitHub / arXiv / public documentation
- Ray-provided notes

## Labels
Use labels consistently:

[Confirmed] official source or strong multi-source confirmation  
[Reported] credible media report, not independently confirmed  
[Background] general technical explanation  
[Analysis] engineering inference or Ray-style interpretation  
[Rumor] social or unverified discussion  

## Default behavior
Default mode must be dry-run.
Never send email unless the user explicitly asks for --send-email.
Never add real SMTP passwords, API keys, or tokens to the repo.
Secrets belong in .env or GitHub Secrets only.

## Required workflow for every code task
When modifying this repo:

1. Modify repo files, not only the generated report.
2. Update tests when behavior changes.
3. Run tests.
4. Run:
   python -m src.main --dry-run --editor
5. Confirm:
   - no email is sent
   - no paywall bypass is added
   - no full article text is scraped or output
6. If tests pass, commit and push to GitHub main.
7. Return the commit hash.

If direct push is not possible, create a pull request.

## Commit message style
Use clear commit messages, for example:
- Update editor report with explain mode
- Add weekly curator workflow
- Improve engineering lens output