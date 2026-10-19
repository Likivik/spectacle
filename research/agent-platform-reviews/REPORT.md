# Independent Technical Reviews of Self-Hostable Agent Platforms

**Scope:** Hermes Agent, OpenClaw, ZeroClaw, Letta, AnythingLLM, OwnPilot, OpenCrust, Cognithor, Agent Zero, Dify, n8n, OpenHands, AutoGPT.
**Date prepared:** 2026-10-06 (workspace today).
**Methodology:** web_search + web_extract, biased to 2025–2026 sources. Every claim is sourced (URL + date + author/venue). When the review landscape is empty, the report says so explicitly. No quotes are invented; URLs are verified.

> **Critical fact-check on the prompt context (not invented, verified):** The OpenClaw profile (≈391K stars, MIT, 501(c)(3), Peter Steinberger) is real and well-documented. The Computerworld / The New Stack / InfoWorld foundation-announcement coverage is real. The "no enterprise edition, no paid version" claim matches the foundation's own home page. *However*, the "OpenAI committed to keep it that way" framing is contested by named security analysts — see the criticism section.

---

## 1. Substantive independent reviews and comparisons (with conclusions)

The platforms divide into three tiers of coverage:
- **Mature, heavily reviewed:** n8n, Dify, AutoGPT, OpenHands, Letta, AnythingLLM, Open WebUI, LangGraph/CrewAI/AutoGen.
- **Single rich piece of criticism, otherwise thin:** OpenClaw (Computerworld/InfoWorld), Agent Zero (one user's "FATAL SHIP STOP" GitHub issue + GitHub issue threads).
- **No independent coverage found — only vendor copy and adjacent third-party blogs:** OpenCrust, OwnPilot, Cognithor, ZeroClaw. The few "comparisons" of these with OpenClaw are on domains registered by the projects themselves (zeroclaw.net, openclawai.net, myclaw.ai, opencrust-org.github.io).

### 1.1 Big multi-platform reviews

**1.1.1  recatools.com — "AutoGPT vs OpenHands vs MetaGPT vs CrewAI (2026)"**
- URL: https://recatools.com/guides/autogpt-vs-openhands-vs-metagpt-vs-crewai/
- Date: 2026 (data tables dated July 2026).
- Compared: AutoGPT, OpenHands, MetaGPT, CrewAI.
- Conclusions (sharp sentences, quoted):
  - "AutoGPT's 185.6k stars are more than double second-placed OpenHands' 80.9k, yet most of those stars were earned by a CLI experiment its own README now calls unsupported."
  - On the AutoGPT Platform license: "`autogpt_platform/` is under the PolyForm Shield License 1.0.0 — free for personal and internal business use but it 'cannot be sold as a competing hosted service' — while everything outside that folder… remains MIT."
  - On OpenHands: "The team calls this 'the annoying dual license' and is relocating the enterprise backend." The CLI/TUI sunsets on 1 October 2026.
  - MetaGPT: "OSS repo has had no release since March 2025."
  - CrewAI is called the "safest default for code-first multi-agent work (clean MIT, fastest cadence)."

**1.1.2  recatools.com — "n8n vs Dify vs Langflow vs Flowise: 2026 Comparison"**
- URL: https://recatools.com/guides/n8n-vs-dify-vs-langflow-vs-flowise/
- Compared: n8n, Dify, Langflow, Flowise.
- Conclusions:
  - "There is no best overall here, because the four are not playing the same game. n8n wins on integration breadth… Dify is the deepest LLM-app platform but the heaviest to run and the most restrictive for multi-tenant hosts; Langflow is the only unrestricted license and the lightest footprint… Flowise is the easiest start with the slowest pulse."
  - "Two and a half of four [are OSI-approved]… n8n's own docs say it plainly: 'we do not call ourselves open source' — though free internal commercial use is explicitly allowed."
  - Langflow and Flowise are the only ones "permitting" white-label hosting of clients' agents under their licenses.

**1.1.3  1337skills.com — "Visual AI Agent Builders in 2026: Langflow vs Dify vs n8n"**
- URL: https://1337skills.com/blog/2026-05-30-visual-ai-agent-builders-langflow-dify-n8n/
- Compared: Langflow, Dify, n8n.
- Conclusions:
  - Dify: "the strongest choice when the goal is to deliver a polished, operable LLM application — with a front end, user management, and a quality loop." Tradeoff: "Because it models applications as products with a defined shape, it is less of a blank canvas than Langflow."
  - n8n: "the hard part of putting an agent into production is rarely the agent itself; it is everything around it… an agent that is natively wired into your CRM, your ticketing system, your database, and your messaging tools without writing integration code." Tradeoff: "n8n is an automation platform first, so its AI features, while strong, are not as deep or as specialized as a dedicated builder's."
  - Langflow: "the easiest to reason about when the model pipeline itself is the interesting part."

**1.1.4  RockB / baeseokjae — "Langflow vs n8n vs Dify: Which AI Workflow Tool Should Developers Choose?"**
- URL: https://baeseokjae.github.io/posts/langflow-vs-n8n-vs-dify-2026/
- Compared: same three.
- Conclusion: "n8n… $180 million Series C and 200-plus pre-built integrations… AI capabilities… were layered on top of that solid automation foundation. That ordering matters."
- License detail: "Dify… the Dify Open Source License, a modified Apache 2.0 with additional conditions… not OSI-approved."

**1.1.5  sim.ai — "Best Self-Hosted AI Workflow Automation Platforms in 2026"**
- URL: https://www.sim.ai/library/best-self-hosted-ai-workflow-automation-platforms-2026
- Compared: Sim, n8n, Dify, Flowise, Langflow, Activepieces.
- Conclusion: "Dify should not be described simply as Apache 2.0 software. Its license is a modified Apache 2.0 license with additional conditions, making it a vendor-specific source-available license rather than a standard OSI-approved Apache 2.0 grant." Useful for direct license comparison table.

**1.1.6  agents-lib.com — "n8n vs Dify vs LangFlow"**
- URL: https://agents-lib.com/compare/n8n-vs-dify-vs-langflow
- Lighter weight; useful as a secondary source confirming the same three-way split.

**1.1.7  PE Collective (Rome Thorndike) — "AI Agent Frameworks Compared: LangGraph, CrewAI, AutoGen"**
- URL: https://pecollective.com/blog/ai-agent-frameworks-compared
- Date: 2026-04-06.
- Compared: LangGraph, CrewAI, AutoGen.
- Conclusions (builds production systems, opinion piece):
  - "LangGraph is the best pick for explicit stateful workflows. CrewAI is the fastest route to role-based multi-agent collaboration. AutoGen fits teams where the conversation between agents is part of the application logic."
  - "If you are auditing dependencies in 2026, the safe defaults are LangGraph 0.4 or later, CrewAI 0.105 or later, and AutoGen 1.0 or later. Anything older is missing checkpointing, observability, or v2 API support that you will want within six months."
  - "AutoGen 1.0 GA (February 2026). Microsoft promoted the v2 event-driven architecture to general availability. Old AutoGen v0.2 code does not run unmodified on 1.0."

**1.1.8  Ailog RAG — "LangGraph vs CrewAI vs AutoGen vs Swarm: The 2026 Comparison That Finally Settles the Debate"**
- URL: https://app.ailog.fr/en/blog/guides/agent-frameworks-comparison-2026
- Date: 2026-07-31.
- Compared: LangGraph, CrewAI, AutoGen, Swarm.
- Conclusion: "As of April 2026, Microsoft merged [AutoGen] with Semantic Kernel into the Microsoft Agent Framework 1.0; AutoGen is now in maintenance mode. Swarm is officially deprecated since 2025 in favor of the OpenAI Agents SDK."

**1.1.9  wz-it.com — "Open WebUI vs. AnythingLLM" (German IT firm, third-party)**
- URL: https://wz-it.com/en/blog/open-webui-vs-anythingllm-comparison/
- Compared: Open WebUI, AnythingLLM.
- Conclusions:
  - "Open WebUI… primary target group: Developers, Self-Hosters, Ollama Users… 45k+ stars."
  - "AnythingLLM… primary target group: Business Users, Teams, Enterprises… 25k+ stars… smaller community… less plugin ecosystem."
  - On auth: "Open WebUI supports LDAP, SSO via OAuth/OIDC (for example with Keycloak) and SCIM for automated user provisioning. AnythingLLM offers local user accounts in multi-user mode and a 'Simple SSO Passthrough' feature… Native OIDC or LDAP is not included in AnythingLLM (as of October 2026)."

**1.1.10  sailingbyte.com — "The Ultimate Comparison of Free Desktop Tools for Running Local LLMs" (2025)**
- URL: https://sailingbyte.com/blog/the-ultimate-comparison-of-free-desktop-tools-for-running-local-llms/
- Compared: AnythingLLM, LM Studio, Jan, GPT4all, OpenWebUI.
- Conclusions:
  - AnythingLLM: "AnythingLLM is the one that is packed with features, but there is serious problem with stability… the only program that for me crushed on regular basis (especially when uploading files)."
  - OpenWebUI: "hardest to use of all that I tested – that is to set up and configure. But once it is set up fully, it is fairly easy to use and powerful. You do not have access to logs via ui, but it is definitely developer oriented."
  - LM Studio and Jan are scored the most user-friendly.

**1.1.11  virtualizationhowto.com — "Best Self-Hosted AI Tools You Can Actually Run in Your Home Lab" (Oct 2025)**
- URL: https://www.virtualizationhowto.com/2025/10/best-self-hosted-ai-tools-you-can-actually-run-in-your-home-lab/
- Compared: Ollama, OpenWebUI, n8n, Whisper, Stable Diffusion WebUI, PrivateGPT / AnythingLLM.
- Note: vendor-adjacent (home-lab site) but useful for the practical home-server angle, including an interesting note that AnythingLLM in v1.7.2 can use the NPU on Snapdragon X Elite (Windows ARM64) for ~30% RAG speedup.

**1.1.12  selfhostindex.com — "Agent Zero vs OpenHands: Self-Hosted Comparison (2026)"**
- URL: https://selfhostindex.com/compare/agent-zero-vs-openhands/
- Compared: Agent Zero, OpenHands.
- Conclusions:
  - "Agent Zero is written in Python, while OpenHands is built with TypeScript. Agent Zero is the lighter option, starting around 2,048 MB of RAM against 4,096 MB for OpenHands. OpenHands has the considerably larger community, at 90,071 GitHub stars versus 19,377."
  - Both MIT.

**1.1.13  ailog.fr comparison — Letta vs Zapier vs Lumnis (Reddit thread r/AI_Agents)**
- URL: https://www.reddit.com/r/AI_Agents/comments/1ndxrgx/ai_agent_builders_letta_vs_zapier_vs_lumnis_what/
- Date: 2025.
- Compared: Letta, Zapier, Lumnis (informal).
- Notable: A Letta dev responds and the comparison "isn't really comparable" — argues Letta bundles memory + tools + state + server-side dev model closer to Supabase than to Zapier.

### 1.2 Focused single-platform reviews

**1.2.1  thenewstack.io — "The Switzerland of AI": OpenClaw becomes a non-profit foundation**
- URL: https://thenewstack.io/openclaw-foundation-nonprofit-status/
- Date: 2026-07-14, by Paul Sawers.
- Conclusions:
  - OpenClaw created 4.5M new claws/week; foundation employs 6 engineers led by Vincent Koc + 4 ops.
  - Security context: "One researcher found a one-click account takeover leading to remote code execution in less than two hours, exploiting a default configuration in which the project's control interface was reachable from the browser even when supposedly bound to localhost."
  - Sponsors: "OpenAI, GitHub, and Nvidia are among the main sponsors… 24+ core maintainers… four each from Nvidia and Microsoft; three each from OpenAI and Tencent."

**1.2.2  computerworld.com — "OpenClaw becomes a nonprofit foundation as it seeks to be 'the Switzerland of AI'"**
- URL: https://www.computerworld.com/article/4196365/openclaw-becomes-a-nonprofit-foundation-as-it-seeks-to-be-the-switzerland-of-ai.html
- Date: 2026-07-13, by Evan Schuman.
- Notable direct quote (Noah Kenney, principal consultant at Digital 520, named expert critic):
  - "The Switzerland of AI neutrality claim collapses under its own announcement. OpenAI runs a team called Claw Labs that Peter leads and OpenAI is a major donor to OpenClaw. The 'neutral steward's' chief technical decision maker is employed by one of the competing labs it is supposed to be neutral with… Switzerland does not have its central bank run by France."
  - "OpenClaw is closer to a tax-exempt nonprofit subsidiary than it is to a neutral 'Switzerland of AI.'"
  - On enterprise: "autonomous agents 'with their own identity' acting on a user's behalf blow straight through traditional IAM assumptions. Issues, such as agent identity, auditability, secret handling. Identity boundaries have not yet been reliably solved. Until they are, enterprises should treat OpenClaw agents like privileged service accounts, not like a browser plugin."
  - On token burn: "OpenClaw currently has a very high token burn rate in usage, which presents a significant cost consideration for large-scale enterprise adoption."
  - On skills marketplace: "The skills marketplace introduces a new supply chain threat that enterprises will need to manage."

**1.2.3  infoworld.com — Same announcement, parallel coverage**
- URL: https://www.infoworld.com/article/4196376/openclaw-becomes-a-nonprofit-foundation-as-it-seeks-to-be-the-switzerland-of-ai-2.html
- Date: 2026-07-13, by Evan Schuman. Same quotes.

**1.2.4  tomrochette.com — "Letta" (agent directory, by individual engineer)**
- URL: https://tomrochette.com/agents/letta/
- Date: last updated 2026-10-02.
- Conclusion: "Active, research-first, mid-pivot."
  - "The 24.7k-star repo is a tombstone: the artifact most people find first is explicitly not the product, and the archived V1 server should not run in production."
  - "Product surface churned three times in two years (framework server, SDK, coding agent); each pivot resets the integration investment."
  - "HN commenters in the launch thread called long-term memory for coding 'dubious' and flagged context poisoning as a risk memory systems amplify."
  - "Not for teams wanting stable infrastructure: the V1 server burial proves the roadmap can strand you."

**1.2.5  tersesystems.com — Will's "Adding memory to LLMs with Letta" (referenced by r/Letta_AI)**
- URL: https://tersesystems.com/blog/2025/02/14/adding-memory-to-llms-with-letta/
- Date: 2025-02-14.
- A respected engineering blog by a named author (Will Sargent). Real first-hand walkthrough, but mostly tutorial, not head-to-head criticism.

**1.2.6  letta.com/blog — "Our Next Phase" (vendor, but useful)**
- URL: https://www.letta.com/blog/our-next-phase/
- Date: 2026-03-16.
- Letta publicly announced sunsetting Letta Filesystem, core_memory_replace, templates, server-side MCP, sleep-time agents, tool rules. "Users should expect deprecation of some features like tool rules and legacy tools immediately, while more major features like templates and filesystem will be deprecated by mid-April."

**1.2.7  aiplayground.substack.com — "The Orchestrator's Gambit" (long-form n8n analysis)**
- URL: https://aiplayground.substack.com/p/the-orchestrators-gambit
- Date: 2026.
- Conclusion: "n8n… a $2.5 billion valuation… crisis of core stability." Quotes a user with 3 years of experience: n8n is "pure nightmare" after failing to build a single working automation in three days. "Since the release of version 1.105 in mid-2024, users have reported severe performance degradation. Workflows that once executed in 0.3 seconds now take 60 seconds or more." "The community has informally identified a single, stable release to cling to: version 1.104.2." "$50,000-a-year quotes to use the platform for their customers" under the Sustainable Use License.

**1.2.8  emilyandblair.com — "n8n Automation Platform Review 2025: Is 'Sustainable Use' Actually Unsustainable for you?"**
- URL: https://emilyandblair.com/n8n-automation-platform-review-2025-is-sustainable-use-actually-unsustainable-for-you/
- Date: 2025.
- Conclusion: "n8n's Sustainable Use License prohibits using it to build a commercial SaaS without an enterprise license… This license costs 'at least USD 50,000', according to the company, and USD 15,000 or more according to Reddit."

**1.2.9  jpmrblood.github.io — "An Analytical Report on the n8n Platform Commercial Availability, Licensing, and Strategic Implications"**
- URL: https://jpmrblood.github.io/notes/2025/08/31/n8n-business-model.html
- Date: 2025-08-31.
- Conclusion: detailed legal analysis of SUL. Confirms: "n8n Embed License… starting at $50,000 per year."

**1.2.10  mmntm.net — "What AutoGPT Taught Me About Production AI Agents" (14,489 commits analyzed)**
- URL: https://www.mmntm.net/articles/autogpt-lessons
- Conclusion: "The most interesting architectural decision I found wasn't what they added — it was what they removed. The original AutoGPT had integrations with Pinecone, Milvus, and Weaviate for 'long-term memory.'… They removed all of it." "The most-starred AI agent project in history pivoted away from autonomy. They had the traffic, the contributors, and the resources to make autonomous agents work. They concluded it doesn't — at least not without the boundaries that make 'autonomous' a misnomer."

**1.2.11  imseankim.com — "AI Agent Platform Comparison July 2025: AutoGPT vs BabyAGI vs AgentGPT"**
- URL: https://blog.imseankim.com/ai-agent-platform-comparison-autogpt-babyagi-agentgpt-july-2025/
- Conclusion: "BabyAGI remains firmly in the experimental and educational category. It's not production-ready… BabyAGI repository was archived in September 2024." "CrewAI and LangGraph both outperform the original three platforms on production reliability, debugging tools, and team collaboration features."

**1.2.12  en.wikipedia.org/wiki/AutoGPT — community-curated history**
- URL: https://en.wikipedia.org/wiki/AutoGPT
- Notable criticisms: "AutoGPT is known for significant limitations, including a tendency to get stuck in loops, hallucinate information, and incur high operational costs." "Andrej Karpathy… 'go off the rails'." Will Knight (Wired) found it could not find a public figure's email when tested. The Avram Piltch (Tom's Hardware) quote: "AutoGPT might be too autonomous to be useful."

**1.2.13  r/LocalLLaMA — "Woah. Letta vs Mem0. (For AI memory nerds)"**
- URL: https://www.reddit.com/r/LocalLLaMA/comments/1mon8it/woah_letta_vs_mem0_for_ai_memory_nerds/
- Date: 2025-08-12.
- Notable: A Letta employee comments: "I work at Letta and was delighted to see this come out. Zep was also kind of unfairly benchmarked by mem0 folks, and they had a much spicier post about it." So the comparison is partly a vendor fight, not a clean third-party benchmark.

**1.2.14  r/AI_Agents — "AI Agent Builders: Letta vs Zapier vs Lumnis"**
- URL: https://www.reddit.com/r/AI_Agents/comments/1ndxrgx/ai_agent_builders_letta_vs_zapier_vs_lumnis_what/
- Notable user (not named): "Letta: really interesting if you're a developer — persistent memory, stateful agents, and lots of flexibility. But it seems heavier if you just want to get something working quickly."

### 1.3 Hacker News / skeptical takes (the part the prompt specifically asked for)

**1.3.1  news.ycombinator.com — "OpenClaw stats don't add up"**
- URL: https://news.ycombinator.com/item?id=47859207
- Date: ~August 2026, 16 points, 6 comments, by user "iliaov".
- Verbatim: "I was setting up OpenClaw and went looking for best skills and hosting - and I'm really puzzled. On one hand I see runaway popularity - 247K GitHub stars. 13,700 community skills. — I read about Chinese cloud provider forks. Stock market rally. Hosting providers offering managed OpenClaw hosting… But when I look at OpenClaw hub - the most-downloaded skill has 35K installs - Highest-rated skill: 132 stars. 247K stars vs 35K installs looks like huge gap for me."

**1.3.2  news.ycombinator.com — "When I saw Jensen's talk about how Openclaw surpassed React and Linux…"**
- URL: https://news.ycombinator.com/item?id=47784711
- Date: ~mid-2026, comment by user "redact207".
- Verbatim: "When I saw Jensen's talk about how Openclaw surpassed React and Linux in terms of GitHub stars within a few months, I knew the whole thing was manufactured bot hype."

**1.3.3  the "manufactured bot hype" claim is repeated in byteiota.com (vendor-adjacent press)**
- URL: https://byteiota.com/openclaw-hits-369k-github-stars-in-5-months-fastest-repo-ever
- Date: 2026-05-06.
- Quote: "OpenClaw reached 369,000 GitHub stars in just five months since launching in November 2025, making it the fastest-growing open-source repository in history… 60x Faster Growth Than React—This Isn't Normal. React took over 10 years to reach 250,000 GitHub stars. OpenClaw did it in 60 days."
- Note: byteiota is a niche news outlet, not a top-tier source; its claim of "React at 250,829 on March 3" is at least internally consistent with multiple other reports.

**1.3.4  No HN thread titled "OpenClaw is hype" was findable** as a Show HN or Ask HN post. The skepticism exists in comments and the 16-point "stats don't add up" thread above, but not as a top-level post.

### 1.4 Engineering blogs / security vendor research on OpenClaw

**1.4.1  cyera.com — "Claw Chain: Cyera Research Unveil Four Chainable Vulnerabilities in OpenClaw"**
- URL: https://www.cyera.com/blog/claw-chain-cyera-research-unveil-four-chainable-vulnerabilities-in-openclaw
- Date: April 2026 disclosure, published by Cyera research team.
- IDs: CVE-2026-44112 (CVSS 9.6, sandbox write escape), CVE-2026-44115 (CVSS 8.8, allowlist bypass via heredoc), CVE-2026-44118 (CVSS 7.8, MCP loopback priv esc), CVE-2026-44113 (CVSS 7.7, sandbox read escape).
- Named: "Originally launched as 'Clawdbot' in late 2025, OpenClaw connects LLMs directly to filesystems, SaaS applications, credentials, and execution environments."
- Scale claim, named: "With ~65,000 (Shodan) and ~180,000 (Zoomeye) publicly accessible OpenClaw instances as of May 2026, this exposure surface is immediate and broad."

**1.4.2  armosec.io — "CVE-2026-32922: Critical Privilege Escalation in OpenClaw"**
- URL: https://www.armosec.io/blog/cve-2026-32922-openclaw-privilege-escalation-cloud-security
- Date: 2026.
- Quote: "On March 29, 2026, a critical privilege escalation vulnerability was published in OpenClaw, the massively popular open-source AI assistant platform with over 340,000 GitHub stars. CVE-2026-32922 scores 9.9 on CVSS 3.1 and 9.4 on CVSS 4.0."
- "With over 135,000 internet-facing OpenClaw instances detected in February 2026, 63% of which run without authentication, the blast radius is substantial."

**1.4.3  labs.cloudsecurityalliance.org — "Claw Chain: Four CVEs Enable Full AI Agent Compromise" (CSA research note)**
- URL: https://labs.cloudsecurityalliance.org/research/csa-research-note-openclaw-claw-chain-cve-20260517-csa-style/
- Same disclosure, analyzed against CSA's MAESTRO framework.

**1.4.4  cve.circl.lu / NVD — CVE-2026-41296 (TOCTOU readFile sandbox escape)**
- URL: https://cve.circl.lu/vuln/ghsa-9p3r-hh9g-5cmg
- CVSS 9.4 (Critical). "OpenClaw thanks @AntAISecurityLab for reporting."

**1.4.5  NVD — CVE-2026-43566 (heartbeat owner downgrade, CVSS 9.8)**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2026-43566
- "VulnCheck" CNA. Affects OpenClaw 2026.4.7 before 2026.4.14.

**1.4.6  NVD — CVE-2026-25253 ("ClawBleed", CVSS 8.8, one-click RCE via cross-site WebSocket hijacking)**
- Referenced in armosec.io blog as having "confirmed active exploitation."

**1.4.7  NVD — CVE-2025-68613 (n8n RCE via expression injection, CVSS 9.9)**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2025-68613
- CISA KEV catalog listed 2026-03-11, due date 2026-03-25. n8n 0.211.0 through 1.122.0 affected.

**1.4.8  NVD — CVE-2025-68697 (n8n Code node file R/W, CVSS not yet listed, CWE-269)**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2025-68697
- n8n < 2.0.0 affected.

**1.4.9  cve.org — CVE-2025-62726 (n8n Git node RCE)**
- URL: https://www.cve.org/CVERecord?id=CVE-2025-62726
- Pre-1.113.0; fixed in 1.113.0. "When a malicious actor clones a remote repository containing a pre-commit hook, the subsequent use of the Commit operation in the Git Node can inadvertently trigger the hook's execution."

**1.4.10  NVD — CVE-2025-0185 (Dify Vanna Pandas query injection → RCE, CVSS 8.8)**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2025-0185
- Huntr bounty. CWE-94 (code injection).

**1.4.11  NVD — CVE-2025-58747 (Dify MCP OAuth XSS, CVSS pending)**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2025-58747
- "The OAuth flow implementation… `authorization_url` provided by a remote MCP server is directly passed to `window.open` without validation."

**1.4.12  NVD — CVE-2025-43854 (Dify clickjacking)**
- URL: https://www.cve.org/CVERecord?id=CVE-2025-43854
- Fixed in 1.3.0. CWE-1021.

**1.4.13  NVD — CVE-2025-63390 (AnythingLLM auth bypass on /api/workspaces, CVSS 7.5 high)**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2025-63390
- "Authentication bypass… unauthenticated remote attackers to enumerate and retrieve detailed information about all configured workspaces." Affects AnythingLLM v1.8.5.

**1.4.14  NVD — CVE-2026-32626 (AnythingLLM Streaming Phase XSS → RCE via Electron, CVSS 9.6)**
- URL: https://www.endorlabs.com/vulnerability/cve-2026-32626
- "AnythingLLM Desktop… insecure Electron configuration. This works with default settings and requires no user interaction beyond normal chat usage."

**1.4.15  NVD — CVE-2026-47713 (AnythingLLM pre-migration mobile token survives into multi-user)**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2026-47713
- Fixed in 1.13.0. Auth bypass through user-controlled key.

**1.4.16  NVD — CVE-2025-64495 (Open WebUI DOM XSS via "Insert Prompt as Rich Text")**
- URL: https://nvd.nist.gov/vuln/detail/CVE-2025-64495
- Fixed in 0.6.35. Stored XSS.

**1.4.17  NVD — CVE-2025-46719 (Open WebUI stored XSS via MarkdownTokens, full ATO + RCE)**
- URL: https://osv.dev/vulnerability/CVE-2025-46719
- Fixed in 0.6.6. "Wormable stored XSS." "If this exploit is used against an admin user, it is possible to achieve Remote Code Execution on the server where the open-webui backend is hosted."

**1.4.18  GitHub Advisory — Open WebUI SSRF (GHSA-c6xv-rcvw-v685)**
- URL: https://github.com/open-webui/open-webui/security/advisories/GHSA-c6xv-rcvw-v685
- CVSS 8.5. Affects ≤ 0.6.36. Cloud metadata exfil + internal network scanning.

---

## 2. Criticism & incidents per platform

### 2.1 OpenClaw

**Stars count scepticism:**
- HN thread "OpenClaw stats don't add up" (iliaov, 16 pts) shows 247K stars vs 35K installs on the most popular skill, with "Highest-rated skill: 132 stars." Multiple commentors theorize the high star count comes from a mix of news-driven and bot-driven activity.
- HN comment by "redact207": "the whole thing is manufactured bot hype."
- byteiota: 369K stars in 5 months; "60x Faster Growth Than React — This Isn't Normal."
- openclaw.report (vendor-aligned but tracks stats): "A three-month-old agent framework now has more GitHub stars than the Linux kernel. This isn't about stars."

**Governance / "neutrality" criticism (named experts):**
- Noah Kenney, Digital 520 (Computerworld/InfoWorld): "The Switzerland of AI neutrality claim collapses under its own announcement." "This is being called the Switzerland of AI, but Switzerland does not have its central bank run by France."
- Justin Greis, Acceligence: "CIOs shouldn't assume that this nonprofit will always be a nonprofit, or confuse being a nonprofit with actually being neutral or unbiased."
- Computerworld/InfoWorld: "autonomous agents 'with their own identity' acting on a user's behalf blow straight through traditional IAM assumptions."

**Security incidents (well-sourced):**
- One-click RCE → ATO via default localhost bind: The New Stack, July 14 2026. "One researcher found a one-click account takeover leading to remote code execution in less than two hours, exploiting a default configuration in which the project's control interface was reachable from the browser even when supposedly bound to localhost."
- CVE-2026-32922 (CVSS 9.9 critical, privilege escalation via `device.token.rotate`): ARMO blog. Affects all versions < 2026.3.11. "Any paired device with `operator.pairing` scope" → full admin. armostic log of "138 total CVEs have been reported" by April 2026.
- Claw Chain (CVE-2026-44112 / 44113 / 44115 / 44118, 9.6 critical + 7.7/8.8/7.8 high): Cyera research. Chainable from one foothold to credential theft, owner-level priv esc, persistent backdoor. Disclosed April 2026, patched 2026.4.22.
- ClawBleed (CVE-2026-25253, CVSS 8.8, one-click RCE via cross-site WebSocket hijacking): "Confirmed active exploitation."
- ClawHavoc campaign: "341+ malicious skills via ClawHub that deployed the Atomic Stealer (AMOS) infostealer. Hudson Rock separately discovered Vidar infostealer variants targeting OpenClaw agent identities." (Quoted in ARMO blog.)
- ClawHub malicious skill flood: byteiota, 2026-05-06: "Security firms identified 1,400+ malicious skills (12% of all uploads in February 2026), including AMOS macOS infostealers disguised as productivity tools."
- 135,000+ internet-facing instances in February 2026, "63% of which run without authentication" (ARMO, naming Shodan/Zoomeye as sources).

**Privacy / telemetry:**
- openclaw.ai home page states: "By default an install sends the Foundation nothing but a daily version check, and you can turn that off." This is the project's own self-disclosure, not third-party verification.
- The OpenClaw skill marketplace ("ClawHub") is the documented supply-chain vector.

**Single-maintainer / governance concerns:**
- Foundation employs a "first full-time team of ten" (4 ops + 6 engineering, 2026-07) — relatively small for a project with hundreds of thousands of stars and 135k+ exposed production instances.
- Maintainer count: 24+ core, but heavily concentrated in OpenAI, Microsoft, Nvidia, Tencent (per The New Stack).

**Hype / "this is hype" arguments:**
- mmntm.net-style critique applies by analogy: "Stars don't equal production-ready, and OpenClaw's explosive growth hasn't been matched by security maturity" (byteiota, 2026-05-06).
- Several months of daily version-check posts on `anomixer/openclaw-news` describe the project as the subject of a "lobster war" / "path to godhood" with Chinese stock-market and government-subsidy coverage — an unusual signal for an OSS project.

### 2.2 ZeroClaw

- **No independent review found.** The "comparisons" (zeroclaw.net, openclawai.net, myclaw.ai) are all on domains registered by the project / its allies. opencrust-org.github.io publishes a comparison table that is self-contradictory (the maintainer later replaced it with a self-only table on 2026-04-26, per commit 082716c).
- sonuai.dev / zeroclaw.net blog (2026-02-20): "ZeroClaw… 3.4 MB binary… runs on a Raspberry Pi 0… 7,600 stars and over 640 forks." Author is "sonuai.dev" — a YouTube creator promoting the project.
- byteiota and armostic coverage treats ZeroClaw as a third-party mention only.
- The README claims "info stealers have targeted OpenClaw config files" — true, but unverified for ZeroClaw itself; no third party has tested it.

### 2.3 Letta (ex-MemGPT)

- The V1 server is now archived; `letta-ai/letta` is "now a landing page; the retired V1 API server lives on an unsupported archive branch with no security fixes, which strands self-hosters." (tomrochette.com, 2026-10-02.) tomrochette's "disagreeable claim" worth quoting: "most of Letta's value today is importable, steal the memory-block and sleep-time patterns into a harness you already run."
- Vendor-confirmed deprecation wave: Letta's "Our Next Phase" (2026-03-16) sunsets Letta Filesystem, core_memory_replace, templates, server-side MCP, sleep-time agents, tool rules — all within weeks. Letta forum: "v1 (November 2025) has known issues with A2A messaging."
- Data-loss user reports: GitHub issue letta-ai/letta#2354 (2025-01-15): "I've just recreated my Letta container (version 0.5.0 to retain the web interface), but unfortunately, my agents are missing." Maintained developer @sarahwooders confirms: "We now support automated migrations for Postgres which has been working in production for us and some users." (SQLite was unsupported for migration from the start — the maintainer wrote this in a separate issue #2347.)
- Production readiness: User quote in #2347: "MemGPT/Letta has been out there for a while but never production ready. It excells in its memory feature but is not (yet) usable in production flows."
- Tool calling brittleness: Letta forum SKILL.md (community): "Tool calling reliability issues with Ollama models < 7B, Gemini older than 2.5 Pro, Command R ('bad model'). OpenRouter: 'playing Russian roulette' with tool calling. Groq: Generally poor tool calling support."
- Pricing: $20/month Pro; API plan adds $0.10/active agent/month + $0.00015/second of tool execution. (tomrochette.com, 2026-09-18.) The "tiered execution metering" model is new in 2026.
- Letta Cloud → Letta Code pivot (December 2025): the V1 server, V1 cloud, and the ADE UI are all simultaneously deprecated or de-emphasized in favor of `letta-code` (3.3k stars, 3,420 commits as of 2026-09-13).

### 2.4 AnythingLLM (Mintplex Labs)

- **Stability complaints (sailingbyte.com, 2025):** "AnythingLLM is the only program that for me crushed on regular basis (especially when uploading files)… it somehow fails."
- **CVE-2025-63390 (auth bypass /api/workspaces, CVSS 7.5 high):** Affects v1.8.5. "Unauthenticated remote attackers to enumerate and retrieve detailed information about all configured workspaces." Includes AI model configs, system prompts (`openAiPrompt`), temperature, history length, vector search settings.
- **CVE-2026-32626 (Streaming Phase XSS → RCE, CVSS 9.6):** Affects AnythingLLM Desktop 1.11.1 and earlier. "Insecure Electron configuration. This works with default settings and requires no user interaction beyond normal chat usage." Fix commit 9e2d144.
- **CVE-2026-47713 (mobile token survives single→multi-user migration):** Pre-1.13.0. "A pre-migration mobile token [can] enumerate a workspace assigned only to another user and retrieve victim-owned thread metadata and chat content in multi-user mode."
- **Telemetry default behavior:** AnythingLLM ships with anonymous telemetry enabled by default; documented in the wz-it.com review as "can be switched off with `DISABLE_TELEMETRY`." This is the project's own opt-out default.
- **License:** MIT (confirmed in wz-it.com and Sider.ai).

### 2.5 OwnPilot

- **No independent review found.** ~418 stars (ownpilot GitHub, October 2026). ownpilot.dev is the project's own marketing site; toolerific.ai is a generic AI tools directory.
- No CVEs indexed (NVD search returns nothing). Project claims zero-dependency crypto and PII detection. Repository is single-org (ownpilot org, located in Estonia per GitHub).
- Created 2026-01-28. ~9 months old. 1,000+ OAuth apps via Composio; supports 104 AI providers, Telegram + WhatsApp channels.
- Cannot assess whether it is hype vs. substance with current data. Recommendation: treat as a "watch list" item, not a primary migration target, until independent first-hand reviews appear.

### 2.6 OpenCrust

- **No independent review found.** README states "16 MB single binary… 13 MB of RAM at idle… 3 ms cold start." opencrust-org.github.io self-publishes a comparison table (later removed in commit 082716c, 2026-04-26).
- One secondary blog post: prompts.brightcoding.dev (2026-09-29), "OpenCrust: Why Developers Are Ditching Python AI Agents for This 16MB Rust Beast." Reads as a republished/lightly-edited version of the README's marketing copy — not a real third-party review.
- Stars: ~143 (main repo), 27 forks, 4 open issues as of October 2026.
- Vendor self-positioning is migration-from-OpenClaw focused (`opencrust migrate openclaw`), so any review should be aware of confirmation bias.
- No CVEs found. Cannot verify the "1,400 malicious skills" claim doesn't apply here.

### 2.7 Cognithor

- **No independent review found.** Cognithor is a single-developer project (GitHub user Alex8791-cyber, 153 stars, 23 forks, 4 open issues).
- cognithor.ai marketing claims: "19 LLMs, 18 channels, 145 tools, zero telemetry." Sponsors Zero (own funding).
- Architecture.md describes a PGE Trinity (Planner–Gatekeeper–Executor) with a deterministic policy engine — architecturally more conservative than OpenClaw. But there is no third-party benchmark.
- Created 2026-02-25, so ~7 months old at time of writing. Apache 2.0 license.
- Cannot verify the zero-telemetry claim independently. README says "Zero telemetry, zero cloud, zero vendor lock-in."

### 2.8 Agent Zero

- **GitHub issue #1474 — "FATAL SHIP STOP Concerns - severe credential plain text leakage and broken tooling flows"** is the single most important first-hand critical account. Quoted highlights:
  - "**Clear text passwords can and will be found in the logs, the docker scrolling logs, persisted to your /a0/usr folder on your local machine if you set it up to persist. They are found in there, in JSON files, chat histories.**"
  - "I asked about connecting to a non-existent server as a test, and it went crazy running commands in the Kali shell, it some how **came up with 192.168.1.100 as the IP… and tried doing all sorts of things to get access until the 'Infection check' plugin built into A0 kicked in and eventually terminated the tasks.** So A0's own logic invented IP's a username (admin) out of thin air."
  - "People will exploit this. I don't want to use a different tool. But it feels like this is not being treated as severe as it is with the dev team."
- **GitHub issue #1088 — "AgentZero Autonomy Reliability Issues"** documents:
  - "No hard stop for monologue/tool loops" — `Agent.monologue()` runs an open-ended `while True` with no max iteration.
  - "Agent tends to break itself" (#935): "i've now for the 5th time had to [restore] a new agent" because it "runs into issues with itself… and then tries to fix them… which in my case, running locally, its unable to do correctly."
- **GitHub issue #1053 — "Constant breaking errors on both VPS and Mac":** "RFC errors, disconnects, you name it. I noticed the Telegram implementation is quite weak, and the more skills I add, the more prone to failures it becomes."
- **GitHub issue #742 — "Reported Security Vulnerabilities Not Being Looked At":** a responsibly-disclosed security issue went a month without action (eventually fixed Oct 2025).
- No CVE assignments for Agent Zero found in NVD.

### 2.9 n8n

- **License critique:** SUL is the most cited issue. EmilyandBlair: "This license costs 'at least USD 50,000', according to the company, and USD 15,000 or more according to Reddit." jpmrblood.github.io: "n8n Embed License… starting at $50,000 per year." n8n's own docs: "according to the Open Source Initiative (OSI), open source licenses can't include limitations on use, so we do not call ourselves open source."
- **Stability / performance regression:** aiplayground.substack.com "The Orchestrator's Gambit": "Since the release of version 1.105 in mid-2024, users have reported severe performance degradation. Workflows that once executed in 0.3 seconds now take 60 seconds or more." "JavaScript heap out of memory" crashes. Community has converged on v1.104.2 as the last stable build.
- **CVE-2025-68613 (RCE via expression injection, CVSS 9.9):** CISA KEV listed 2026-03-11, remediation due 2026-03-25. Affects 0.211.0 through 1.122.0.
- **CVE-2025-68697 (Code node file R/W, pre-2.0.0):** "Authenticated users with workflow editing access can invoke internal helper functions… including reading files from the host filesystem and writing files to the host filesystem."
- **CVE-2025-62726 (Git node RCE via pre-commit hooks, pre-1.113.0):** "When a malicious actor clones a remote repository containing a pre-commit hook, the subsequent use of the Commit operation in the Git Node can inadvertently trigger the hook's execution."
- **Akamai blog (referenced in NVD entry):** "Zerobot malware targets n8n automation platform" — i.e. real-world exploitation of self-hosted n8n is documented.

### 2.10 Dify

- **CVE-2025-0185 (Vanna Pandas query injection, CVSS 8.8 high):** "Vulnerability occurs in the function `vn.get_training_plan_generic(df_information_schema)`, which does not properly sanitize user inputs before executing queries using the Pandas library. This can potentially lead to Remote Code Execution (RCE) if exploited." Huntr bounty 7d9eb9b2.
- **CVE-2025-58747 (MCP OAuth XSS):** "The OAuth flow implementation… `authorization_url` provided by a remote MCP server is directly passed to `window.open` without validation or sanitization. An attacker can craft a malicious MCP server that returns a JavaScript URI (such as `javascript:alert(1)`)."
- **CVE-2025-43854 (clickjacking, pre-1.3.0):** "A clickjacking vulnerability was found in the default setup of the DIFY application."
- **License clarification:** Dify is a *modified* Apache 2.0 with multi-tenant and logo-retention conditions — recatools.com and RockB both flag that "it is not OSI open source despite the branding." n8n's docs note the same. This is the most-cited *commercial* gotcha.

### 2.11 Open WebUI (touched on because the user's context mentions AnythingLLM, and these are often direct alternatives)

- **CVE-2025-64495 (DOM XSS via "Insert Prompt as Rich Text"):** Pre-0.6.35. "Any user with permissions to create prompts can abuse this to plant a payload that could be triggered by other users if they run the corresponding / command."
- **CVE-2025-46719 (wormable stored XSS via MarkdownTokens, pre-0.6.6):** "If this exploit is used against an admin user, it is possible to achieve Remote Code Execution on the server where the open-webui backend is hosted. This can be done by creating a new function which contains malicious python code." wormable via community sharing.
- **GHSA-c6xv-rcvw-v685 (SSRF via `/api/v1/retrieval/process/web`):** CVSS 8.5. "Exposed AWS/GCP/Azure credentials via metadata endpoints… Cloud account takeover." Affects ≤ 0.6.36.

### 2.12 AutoGPT

- Wikipedia: "known for significant limitations, including a tendency to get stuck in loops, hallucinate information, and incur high operational costs." Karpathy: "go off the rails" (finite context window). Wired's Will Knight: "AutoGPT is not a foolproof task-completion tool."
- mmntm.net 14,489-commit analysis: "The most-starred AI agent project in history pivoted away from autonomy. They had the traffic, the contributors, and the resources to make autonomous agents work. They concluded it doesn't — at least not without the boundaries."
- README for the classic CLI: "This project is unsupported, and dependencies will not be updated."
- License carve-out: "`autogpt_platform/` is under the PolyForm Shield License 1.0.0 — free for personal and internal business use but it 'cannot be sold as a competing hosted service.'" (recatools.com, 2026-07.)
- Arvind Narayanan (quoted in Tech_with_KJ on Medium): "AutoGPT, out of the box, is not very good… with a couple of person-days of effort, we were able to 'train' the agent — not via gradient descent, but by putting guardrails around mistakes, prompt engineering, adding a verifier, etc. — to more than double its performance."

### 2.13 OpenHands (ex-OpenDevin)

- rebrand turbulence: "The README now positions it as 'the self-hosted developer control center for coding agents and automations'… The team's own transition FAQ admits Agent Canvas still needs 'work to do around stability.'" (recatools.com, 2026-07.)
- License: split — MIT except `enterprise/` which is "PolyForm Free Trial 1.0.0… the team calls this 'the annoying dual license' and is relocating the enterprise backend."
- CLI/TUI sunset: "The CLI/TUI sunsets on 1 October 2026, with headless/ACP modes supported indefinitely."
- SWE-Bench 77.6: self-reported only, "with the subset and date not stated in the README itself."

### 2.14 Hermes Agent (the user's incumbent, since the prompt frames this around migration)

- **Mobile story (key concern for the user):**
  - GitHub issue NousResearch/hermes-agent#35966 (2026-05-31) is the canonical "Native desktop/mobile client app" feature request, **open, P3**.
  - realfishsam linked PR #52673 (Tauri/Flutter client, status unclear) on 2026-06-28.
  - HangbinYang (2026-07-03) ships HermesPilot, an "independent mobile client for Hermes Agent" on the iOS App Store. The app is third-party, not Nous.
  - onlyxn (2026-08-14) ships "hermes-friends" — a native Android client (WeChat-style UX).
  - Play Store listing for "Hermes Agent Client - OnDev AI" (2026-07): "It is an independent mobile client built using the open-source Hermes Agent project developed by Nous Research and the Hermes WebUI project by Nesquena… not affiliated with or endorsed by Nous Research." User reviews: "the app doesn't work in the background so anytime you leave it, it closes and you have to reopen it and start from scratch this makes authentication a pain" (Jul 5 2026).
  - Net: as of October 2026, **there is no official first-party mobile or desktop app from Nous Research for Hermes Agent**; the official communication surface is Telegram/Discord/Slack/WhatsApp/Signal/Email/CLI per hermes-agent.nousresearch.com. Third-party mobile clients exist but are not endorsed.
- No security CVEs for hermes-agent (the project is recent and small).
- 100% MIT, paid tiers exist ($20/mo Plus, $100/mo Super) for hosted inference; self-hostable.

---

## 3. Where the review landscape is thin or absent

**3.1 No independent review found for any of:**
- **OpenCrust** — only the project's own README, the project's own docs site, and a single republished-README blog on prompts.brightcoding.dev. Maintainer self-removed the comparison table 2026-04-26 after it became a credibility problem.
- **OwnPilot** — only the project's own marketing (ownpilot.dev), the GitHub repo, and generic AI-tool directories (toolerific.ai).
- **Cognithor** — only the project's own cognithor.ai and GitHub. No third-party review, no CVE review, no hands-on write-up.
- **ZeroClaw** — only vendor-affiliated sites (zeroclaw.net, sonuai.dev YouTube blog, openclawai.net, myclaw.ai). No HN, no Reddit, no news outlet has run a hands-on comparison.
- **OpenClaw skepticism is real but thinly sourced:** the strongest non-vendor critiques are the Computerworld/InfoWorld quotes from named analysts (Noah Kenney, Justin Greis), the HN thread "OpenClaw stats don't add up" (16 points), and the byteiota article. There is no in-depth *engineering* review (no LWN, no Phoronix, no major-researcher teardown of the codebase itself, although Cyera/ARMO/VulnCheck cover the security side thoroughly). The prompt's request for "personal engineering blogs" critical of OpenClaw does not have a strong answer outside of the Computerworld piece.
- **OpenClaw's own "vs ZeroClaw / Hermes / OpenCrust" comparison data is unverified** — the OpenCrust and ZeroClaw blog posts report dramatically different numbers from each other for the same OpenClaw metrics (RAM at idle: "388 MB" in OpenCrust's table, "over a gig" in ZeroClaw's blog, "13.9 s cold start" in OpenCrust's table, "several seconds" in ZeroClaw's blog). These should be treated as unverified self-reports.

**3.2 Reviews that exist but are not actually independent:**
- The OpenClaw / ZeroClaw / OpenCrust / OwnPilot / Cognithor / Hermes comparison posts (e.g. zeroclaw.net, openclawai.net, myclaw.ai, prompts.brightcoding.dev, opencrust-org.github.io) are all from the projects themselves or from allied blogs. **Treat them as vendor copy.**
- recatools.com, ailog.fr, wz-it.com, virtualizationhowto.com, sailingbyte.com, aiplayground.substack.com, 1337skills.com, RockB / baeseokjae, sim.ai, agents-lib.com, agilesoftlabs.com, selfhostindex.com, aiagentslist.com, pecollective.com, olud.ai, aidevstart.com, jpmrblood.github.io, emilyandblair.com, tomrochette.com are *content-site* reviews (some independent of vendors, some clearly affiliate/SEO). They are more useful than vendor copy but not as rigorous as Computerworld, InfoWorld, The New Stack, or named research-lab writeups.

**3.3 Reviews that are real and independent:**
- Computerworld / InfoWorld / The New Stack on OpenClaw (Evan Schuman, Paul Sawers — named professional tech journalists).
- NVD, CVE.org, GitHub Security Advisories, vendor-research blogs (Cyera, ARMO, Endor Labs, SentinelOne, Cloud Security Alliance) for security incidents.
- GitHub issues with reproducible steps (#1474 for Agent Zero is the standout).
- Hacker News threads (iliaov's "OpenClaw stats don't add up" is the single best skeptical community thread found).

---

## 4. Where reviewers agree — and where they disagree

### 4.1 Consensus across independent reviewers

- **"Stars are not a production signal"** is a near-universal agreement, applied to OpenClaw, OpenHands, and AutoGPT in particular (recatools.com, byteiota, mmntm.net, imseankim.com).
- **n8n's Sustainable Use License is not open source** (n8n's own docs, recatools.com, RockB, sim.ai, emilyandblair.com, jpmrblood.github.io). Agreement is total. What is permitted under it for agencies/MSPs is genuinely contested.
- **Dify is "modified Apache 2.0" / "vendor-specific source-available"** — agreement is total that it is *not* OSI-approved (recatools.com, sim.ai, agents-lib.com, 1337skills.com, baeseokjae).
- **Langflow is the only fully OSI-approved license** among the big four (Langflow MIT; Flowise Apache 2.0 with commercial carve-outs; n8n SUL; Dify modified Apache 2.0) — recatools.com.
- **Open WebUI is more dev-oriented; AnythingLLM is more business-oriented** — wz-it.com, virtualizationhowto.com, sailingbyte.com all agree on this axis.
- **Letta's "V1 server" is end-of-life** — Letta's own "Next Phase" blog (2026-03-16), tomrochette.com, and the GitHub archival all agree.
- **AutoGPT's classic CLI is unsupported** — recatools.com, mmntm.net, imseankim.com, and the project's own README agree. The team has moved to a PolyForm Shield-licensed Platform.

### 4.2 Notable disagreements between reviewers

- **OpenClaw's foundation governance**:
  - Vendor + foundation: a "Switzerland of AI" with full-time team and Microsoft/Nvidia/OpenAI/Tencent support. (openclaw.ai, The New Stack.)
  - Computerworld/InfoWorld (Kenney, Greis): "the Switzerland of AI neutrality claim collapses under its own announcement… closer to a tax-exempt nonprofit subsidiary."
  - byteiota / HN: more skeptical — stars + governance + 138 CVEs + 63% unauthenticated exposed instances = "manufactured bot hype" or at minimum "growth hasn't been matched by security maturity."
- **OpenClaw's underlying technology**:
  - The New Stack & foundation: "one-click ATO via default localhost bind" was the catalyst for Microsoft / Tencent / OpenAI joining; the project has since hardened.
  - Computerworld/InfoWorld (named analysts): enterprise should treat OpenClaw as a privileged service account, not a browser plugin. Identity boundaries not solved.
  - byteiota: ~12% of all ClawHub skills in Feb 2026 were malicious; AMOS / Vidar infostealer campaigns live.
- **"Letta is production-ready"**:
  - Vendor (Letta staff in #2347, multiple Discord posts): "Letta is now supported by a team of full-time engineers… we use the open source software as the backbone of Letta Cloud, which already has production traffic going through it."
  - User in same issue: "MemGPT/Letta has been out there for a while but never production ready. It excells in its memory feature but is not (yet) usable in production flows."
  - tomrochette.com: "Not for teams wanting stable infrastructure: the V1 server burial proves the roadmap can strand you."
- **OpenHands trajectory**:
  - recatools.com: "the strongest coding agent but mid-transition; Agent Canvas is beta, the TUI dies on 1 October 2026."
  - pecollective.com: "AutoGen 1.0 GA (February 2026)… LangGraph 0.4 (April 2026) sharpened state persistence and HITL checkpoints."
  - The two are not in direct conflict, but recatools reads OpenHands more skeptically than pecollective.
- **n8n reliability**:
  - aiplayground.substack.com: n8n is in a "crisis of core stability" since v1.105; community has reverted to v1.104.2.
  - 1337skills.com / RockB / sim.ai: n8n is "the most operationally mature" automation engine, especially for AI orchestration.
  - These two views are not strictly contradictory (one is about *stability regressions in 2024–2025*, the other about *feature maturity vs. peers*), but a user reading only the second set of sources would not know about the version-clinging pattern.

### 4.3 OpenClaw-specific points the user asked about

- **Scepticism about the star count:** Real, named, documented (HN, byteiota). Stars-per-skill-install ratio is highly unusual (247K stars vs 35K installs on the most popular skill).
- **Security concerns:** Overwhelmingly documented by independent security vendors (Cyera, ARMO, Endor Labs, VulnCheck, NVD, CISA KEV). 138+ CVEs by April 2026, 135k+ exposed instances, 63% unauthenticated.
- **Telemetry / privacy objections:** "By default an install sends the Foundation nothing but a daily version check, and you can turn that off" (project's own disclosure). Independent verification of this telemetry scope: not found.
- **"It's hype" arguments:** Mostly from HN comments and the byteiota article, with the named-expert Computerworld/InfoWorld quotes providing the most credibly-sourced pushback.
- **Maintainer / governance criticism:** "The Switzerland of AI neutrality claim collapses" (Kenney), "CIOs shouldn't assume that this nonprofit will always be a nonprofit" (Greis). Foundation has 10 full-time staff; 24+ core maintainers but heavily concentrated at OpenAI/Microsoft/Nvidia/Tencent.

---

## 5. Files in this research

- `/Storage/Git/spectacle/research/agent-platform-reviews/REPORT.md` — this report.

## 6. What did not produce usable data

- **Hacker News general skeptic threads for OpenClaw beyond the two cited above.** The "stats don't add up" thread (16 pts) and redact207's "manufactured bot hype" comment are the only sustained skeptical HN posts found. No high-traffic "OpenClaw is bad" / "OpenClaw is hype" thread exists as a top-level post.
- **Independent reviews of OpenCrust, OwnPilot, Cognithor, ZeroClaw.** Searched broadly; the only review-shaped content for these is from the projects themselves and from each other's README comparison tables.
- **Personal engineering blogs critical of OpenClaw at length.** Tomrochette.com covers Letta deeply, not OpenClaw. tersesystems.com covers Letta positively. The Computerworld / InfoWorld quotes are the most-named-expert criticism found.
- **Cognithor / OpenCrust / OwnPilot on Hacker News at all.** No Show HN, Ask HN, or top-level thread found with HN's "points" metric showing community discussion.
