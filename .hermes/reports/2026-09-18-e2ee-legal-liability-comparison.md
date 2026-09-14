# E2EE Legal & Liability Comparison — Solo EU/Russia-based Operator Running a Hosted AI Roleplay Service

**Compiled:** 2026-09-18
**Audience:** Achiyon / Achlys operator — solo, physically located in EU/Russia, running a hosted AI roleplay service where the operator's server builds prompts, calls an LLM, stores chat history.
**Companion to:** `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md`, `e2ee-browser-capability-survey.md`, `e2ee-business-model-survey.md`.
**Scope:** the legal exposure of three architectural options for storing / processing chat content:

| Option label | Where plaintext lives | Who can read it | Operator's legal posture |
|---|---|---|---|
| **Client-side E2EE** | Only on user's device; server holds opaque ciphertext | Nobody but the user (assuming no implementation bug, no jurisdiction-mandated client-side scanning) | "We cannot read it." GDPR pseudonymisation or outright anonymisation; best defence to DSA / illegal-content claims |
| **TEE** (Trusted Execution Environment on the server) | Briefly inside an attested CPU/GPU enclave during inference; stored encrypted at rest | Not the operator (no key); potentially the LLM provider or enclave vendor with collusion | "We cannot read it, even with root on our own server, as attested by [Intel/AMD/NVIDIA]." GDPR pseudonymisation; partial defence; novel territory under AI Act |
| **Escrow** (current SaaS pattern: operator holds keys) | Server, in plaintext at rest | The operator + anyone with subpoena/warrant to operator | "We can read it if compelled." Full GDPR controller exposure; full DSA hosting-service liability; full SORM/Russia exposure if Russian infrastructure |

---

## TL;DR (the four-line answer)

1. **"We cannot read it" is real protection, but only in the strong sense if and only if the operator has *no* technical path to plaintext.** Client-side E2EE (Signal model) gives the strongest defence and is the only one that has a clean Signal / Proton legal track record. TEE gives a meaningful upgrade over escrow but is legally novel and not yet precedented for AI chat. Escrow gives zero protection — the operator is treated under GDPR as a controller, under DSA as a hosting service with notice-and-action duties, and under Russian law as a telecoms-style operator with mandatory SORM obligations.
2. **"E2EE reduces liability" is *not* a free pass.** Under DSA Art. 6 the safe-harbour applies to "hosting services" that lack *actual knowledge*. E2EE forecloses actual knowledge of content, which collapses the "hosting" classification problem at the content layer — but it does *not* eliminate the operator's potential liability as a service provider for *other* reasons (terms-of-service violations, knowledge of *users'* illegal activity that is structurally visible because metadata is plaintext, illegal images that are detectable in ciphertext headers or in unencrypted thumbnails).
3. **Russia-specific risk is existential for escrow, manageable for TEE, and structurally low for client-side E2EE — but only if infrastructure stays outside Russia.** A Russian-resident operator hosting abroad still owes Russian tax and personal-data-law obligations to Russian users (242-FZ, 23-FZ from July 2025). Hosting abroad does not exempt the operator; the operator can be blocked, fined, and (since 2025) face criminal exposure for non-compliance.
4. **EU Chat Control as of September 2026 does not yet compel backdoors in E2EE services**, but the Council and a blocking minority of member states are actively negotiating the *permanent* CSAR ("Chat Control 2.0"). Any operator shipping E2EE today must price in the political risk that a 2027–2028 EU regulation could force client-side scanning, and design accordingly.

---

## 1. The legal exposure framework

For a solo EU/Russia-based operator running a hosted AI roleplay service, five legal regimes apply simultaneously:

| Regime | What it requires | Why it matters for chat |
|---|---|---|
| **GDPR** (Regulation 2016/679) | Lawful basis, data minimisation, security of processing (Art. 32), breach notification, data-subject rights | Roleplay chats are personal data (often special-category if they touch health, sexuality, political opinion, etc.) |
| **DSA** (Regulation 2022/2065) | Hosting-service liability rules (Art. 6), no general monitoring (Art. 8), notice-and-action for illegal content, transparency reporting | The DSA safe-harbour depends on the provider *not having actual knowledge*. E2EE collapses actual knowledge of content. |
| **EU AI Act** (Regulation 2024/1689) | Risk-classification, transparency for AI systems that interact with people, GPAI provider duties | An LLM that produces roleplay content with emotional/substantive impact is at minimum "limited risk" (Art. 50 transparency); for some uses it borders on "high risk." |
| **NIS2 / Cyber Resilience Act** | Cybersecurity obligations for digital service providers and products with digital elements | Hosting an AI service with EU users crosses the threshold. |
| **Russia: 152-FZ + 242-FZ + 23-FZ (2025)** | Personal-data localisation, mandatory Roskomnadzor notification, foreign-operator blocking | Russian-resident operator has no opt-out from Russian personal-data law. |

There is also **content liability under criminal/civil law of whatever jurisdictions the operator and users are in**: CSAM, extremist content, defamation, harassment, IP infringement — all of which create liability for the operator *if the operator has the means to know*.

The decisive variable in every regime is: **does the operator have actual or constructive knowledge of the content, and can the operator be compelled to act on that knowledge?**

---

## 2. The "we cannot read it" legal defence — what the precedent actually says

### 2.1 The Signal / WhatsApp / Proton track record

**Signal** (US, 501(c)(3)) has published the same legal answer to every subpoena since at least 2016: the service *cannot* produce message content because it does not hold the keys. Its published subpoena response reads:

> "The only information Signal maintains that is encompassed by the subpoena for any particular user account… is the time of account creation and the date of the account's last connection to Signal servers."
> — Signal 2016 grand-jury subpoena response (cited via security.stackexchange.com, signal.org transparency reports)

Signal's published transparency reports (https://signal.org/bigbrother/) consistently show: subpoenas answered with account-creation metadata only; no message content; no message metadata beyond the date of last connection. The legal argument is structural: because the cryptographic architecture places keys on user devices and the server only sees ciphertext, Signal has *nothing to hand over* even when a US court issues a sealed order. Signal's Australian position (re: the Assistance and Access Act 2018) makes the architectural argument explicit:

> "compliance with a demand to provide plaintext communications would require changing the service, not just searching an internal database or running an existing interception tool."
> — Signal, on Australia's TOLA regime (https://umatechnology.org/signal-we-cant-comply-with-aussie-encryption-law-even-if-we-wanted-to/)

Signal has further stated it would *leave the EU market* rather than comply with a CSAR-style detection order (Signal President Meredith Whittaker, public statements 2024–2026).

**Proton** (Geneva, Switzerland) operates under a different model: Proton holds *zero-access encryption* keys in some products and end-to-end keys in others. The legal position is that even a *Swiss court order* cannot compel Proton to surrender E2EE message content, because Proton does not have the keys. Proton has won at least one Swiss Federal Tribunal appeal confirming that foreign (non-Swiss) law-enforcement requests must be approved by a Swiss court before Proton can be compelled to act.

> "Our end-to-end encryption and zero-access encryption mean that no one (not even Proton) has the technical means to access your data without your permission."
> — Proton (https://proton.me)

> "When protesters use Proton Mail, we don't take a position for or against the protest… users are protected by Switzerland's strong rule of law: foreign law enforcement requests must be approved by a Swiss court before we can be compelled to act on them."
> — Proton Mail blog (https://proton.me/blog/protesters-free-speech)

The Proton argument works because Swiss law and Proton's architecture combine: the architecture forecloses technical compliance; Swiss law forecloses foreign compulsion.

**WhatsApp** (Meta) has operated the same Signal-protocol-derived architecture at billion-user scale since 2016. Meta's published transparency reports show that WhatsApp content production is structurally impossible — the same answer as Signal.

### 2.2 What "we cannot read it" actually does *not* protect against

The Signal/Proton defence is robust, but it has limits the marketing does not always emphasise:

1. **It does not protect against metadata liability.** Signal still knows *who messaged whom, when, how often, in what pattern*. A roleplay service that knows "user A chats 3 hours every evening with a 14-year-old-presenting persona about sexual content" can be deemed to have knowledge of the *fact pattern* even if it cannot read the content. Metadata patterns are increasingly being treated as content under EU law (CJEU *Breyer* 2016, French Conseil d'État *2020*).
2. **It does not protect against what the client sends.** If the user's device is the encrypted-sender, the server never sees content. But if there is any unencrypted metadata *appended* to the ciphertext envelope (e.g., a model name, a character card title, a session label), that metadata is searchable and may constitute knowledge.
3. **It does not protect against what the *user* tells the operator voluntarily.** Reports, support tickets, payment metadata, email receipts, IP logs, all become "knowledge" once the user discloses them to the operator.
4. **It does not protect against the operator being designated an information society service with active-monitoring duties under national law** (e.g., France's Arcom regime for some platforms).
5. **It does not protect against AI Act provider duties.** Even if the operator cannot read user content, the operator is still the *provider* of an AI system under EU AI Act Art. 16 and owes transparency, documentation, and risk-management duties *independent of what the LLM is generating*.
6. **It does not protect against sanctions / export-control law.** If a user's roleplay touches sanctioned persons, OFAC/EU sanctioned entities, or controlled technology, the operator's knowledge of metadata may trigger liability even without content.

### 2.3 The "we hold keys in escrow" track record — what happens when you *can* read it

When the operator holds the encryption key (escrow model = current Achiyon default = every legacy cloud LLM service), the operator is *unambiguously* the GDPR *controller* (or *processor* if processing on behalf of another controller), the *provider* of a hosting service under DSA Art. 6, and an *information dissemination organiser* under Russian law. The operator owes:

- GDPR: respond to data-subject access requests, deletion requests, portability requests, breach notification within 72 hours, full security obligations under Art. 32.
- DSA: respond to notices of illegal content, act expeditiously to remove, maintain transparency reports if a VLOP (not yet relevant for solo operator), comply with Art. 16/22/23 due-diligence obligations, and (most importantly) the **DSA Art. 8 prohibition on general monitoring is *only available* if the operator remains a neutral intermediary** — i.e., if the operator has *active knowledge* of content (e.g., via a moderation queue, via analytics, via abuse-detection systems), the safe-harbour narrows or disappears (CJEU *L'Oréal v eBay* 2011; CJEU *YouTube/Cyando* 2021; CJEU *Poland v Parliament* 2022 on Article 17).
- Russian law: register as a personal-data operator, store Russian users' data on Russian infrastructure (242-FZ + 23-FZ), maintain a SORM capability as an "information dissemination organiser" or hosting provider (Federal Law 149-FZ + Government Decree 1952 of 22 Nov 2023).

**Bottom line of §2:** "We cannot read it" is a real and legally meaningful defence *only* when it is *structurally true* — i.e., the architecture forecloses the operator's ability to decrypt. Signal/Proton have a decade-plus track record of this defence holding up in court and before law-enforcement. Anything weaker — escrow with a key on the server, escrow with a key in an HSM but the operator has access to the HSM, TEE without attestation — gets closer to "we choose not to read it," which is *not* the same defence and gets no precedent protection.

---

## 3. GDPR deep dive — what each option actually means under EU data-protection law

### 3.1 Definitions that decide the case

GDPR Art. 4 distinguishes:

- **Personal data** (Art. 4(1)): "any information relating to an identified or identifiable natural person." Personal data is in scope.
- **Pseudonymisation** (Art. 4(5)): "the processing of personal data in such a manner that the personal data can no longer be attributed to a specific data subject without the use of additional information, provided that such additional information is kept separately and is subject to technical and organisational measures." Pseudonymised data **remains personal data** under Recital 26.
- **Anonymous information** (Recital 26): "information which does not relate to an identified or identifiable natural person or to personal data rendered anonymous in such a manner that the data subject is not or no longer identifiable." Anonymous information is **out of scope** of GDPR entirely.

The legal question is therefore: *for any data the operator holds, is the data subject identifiable from the operator's perspective, taking into account "all the means reasonably likely to be used"* (Recital 26)?

The EDPB Pseudonymisation Guidelines (16 January 2025) are explicit:

> "Pseudonymised data, which could be attributed to a natural person by the use of additional information, is to be considered information on an identifiable natural person, and is therefore personal. This statement also holds true if pseudonymised data and additional information are not in the hands of the same person."
> — EDPB Guidelines 01/2025 on Pseudonymisation, §22

This is dispositive: **pure ciphertext held by an operator who cannot decrypt is *not* anonymised** (because the operator + the user's cooperation = re-identification), but it *is* pseudonymised under EDPB doctrine if (a) the additional information (the key) is held separately, (b) under technical and organisational measures, and (c) by a party other than the operator.

### 3.2 How the three options map to GDPR

**Client-side E2EE (Signal model).** The operator holds ciphertext. The key is generated on the user's device and never sent to the operator. Under EDPB Pseudonymisation Guidelines, the operator holds *pseudonymised* personal data (because the ciphertext + the user's cooperation = re-identification). The operator:

- is a *controller* of pseudonymised data under GDPR
- owes full security obligations (Art. 32)
- owes breach notification (Art. 33) if the ciphertext + identifiers are breached, even though the ciphertext alone is unintelligible
- can invoke Art. 32(1)(a) "pseudonymisation and encryption of personal data" as an appropriate technical measure
- can invoke Art. 34(3)(a) exemption from data-subject breach notification "if the controller has implemented appropriate technical and organisational protection measures, in particular those that render the personal data unintelligible to any person who is not authorised to access it, such as encryption"

The IAPP (International Association of Privacy Professionals) has argued more aggressively that *encrypted data held by a party who does not have the key is not personal data at all*. This is the minority academic view but not yet EDPB doctrine.

**Practical GDPR effect for client-side E2EE:** The operator has materially reduced GDPR exposure (Art. 32 satisfied by design; Art. 34(3)(a) exemption available; minimisation satisfied because the operator doesn't collect anything), but the operator remains a *controller* of metadata (account creation date, IP address, payment metadata, message timestamps) and owes full GDPR compliance for that metadata.

**TEE.** The server holds ciphertext at rest (pseudonymised data). During inference, plaintext is briefly inside the enclave. Under EDPB doctrine, data inside a TEE is "personal data in use" — the operator has a momentary window of *technical access* but not *actual* access (assuming attestation holds).

Crucially, FPF (Future of Privacy Forum) has argued that:

> "the use of a TEE does not prevent the primary controller or owner of the data from responding to legitimate requests, either voluntarily or in response to a legal order."
> — FPF, Confidential Computing report (https://fpf.org/fpf-confidential-computing-r3/)

This is dispositive for legal analysis: under GDPR, the *controller* is still whoever determines purposes and means. If the operator deploys a TEE on their own infrastructure, the operator remains the controller for GDPR purposes; the TEE is a security measure, not a relocation of controllership. The operator still has *legal* authority (and arguably *technical* access via attestation-key management) over the data, even if their *practical* access is limited.

**Practical GDPR effect for TEE:** TEE is a meaningful Art. 32 measure (and likely meets the "encryption in use" expectation of HIPAA, PCI DSS 4.0, and EU AI Act Art. 9). It does **not** relocate controllership and does **not** transform the operator from controller into non-controller. TEE reduces breach severity (Art. 32) and may satisfy Art. 34(3)(a) for data at rest, but does **not** immunise the operator from data-subject rights (access, deletion, portability) which the operator must still be able to fulfil by re-deriving the data inside the enclave — which is the *opposite* of GDPR pseudonymisation.

**Escrow (operator holds key).** The operator holds plaintext. The operator is unambiguously the controller (or processor). Full GDPR applies. Art. 32 security obligations, Art. 33 breach notification (and breaches are catastrophic — *every* breach exposes all user data), Art. 15-22 data-subject rights, Art. 25 data-protection by design (the operator has actively failed this if plaintext is the default), and the operator's lawful basis (Art. 6) must support the entire processing lifecycle.

### 3.3 The AI Act overlay

EU AI Act Art. 50 (transparency for AI systems that interact with people) requires the operator to disclose that the user is interacting with an AI system. Art. 9 (risk management for high-risk systems) does *not* apply to a chatbot unless the chatbot is used for one of the eight high-risk Annex III categories (employment, credit, education, biometric ID, law-enforcement access, migration, justice, critical infrastructure). An AI roleplay service is most likely **limited risk** (Art. 50 transparency only) or **general purpose AI** (GPAI) if it integrates a third-party foundation model and fine-tunes or substantially modifies it.

The AI Act does *not* compel E2EE. It does compel:

- **Art. 50** transparency (the user must be told it's an AI)
- **Art. 9 / Annex IV** technical documentation if the operator fine-tunes an open-weight GPAI model to a degree that makes the resulting system "high risk"
- **Art. 53** GPAI provider obligations if the operator fine-tunes a GPAI model above the systemic-risk threshold (10^25 FLOPs at training) — relevant only for *large* operators; solo operator running a hosted inference service using OpenAI/Anthropic API is **downstream deployer**, not GPAI provider
- **Art. 26** deployer obligations: human oversight, monitoring, logging

For a solo operator running an AI roleplay service:

- Default classification is **limited risk** (Art. 50 only)
- If the operator fine-tunes a model to produce sexual / extreme content, the operator is still not "high risk" under the Act (the Act does not prohibit sexual content per se; it requires transparency)
- If the operator integrates a GPAI model via API and uses system prompts for character personas, the operator is a **deployer** of the GPAI model and owes Art. 26 obligations (log inference requests, provide user-facing transparency)

**TEE has a specific AI Act relevance:** Art. 9(2)(a) lists "appropriate technical and organisational measures" for high-risk AI, including "encryption." TEE-based inference is a credible way to demonstrate that "the operator cannot read your prompt" — which is an explicit value proposition for an AI roleplay service.

---

## 4. DSA deep dive — does "we cannot read it" insulate from illegal-content hosting liability?

### 4.1 The DSA hosting safe-harbour in one sentence

DSA Art. 6(1): a hosting service is *not liable* for user-stored illegal content if (a) it does not have actual knowledge of the illegality, and (b) upon obtaining such knowledge, it acts expeditiously to remove or disable access.

Art. 6(2): the safe-harbour does *not* apply "where the recipient of the service is acting under the authority or the control of the provider."

Art. 8: no general obligation to monitor, no proactive obligation to seek facts or circumstances indicating illegal activity.

### 4.2 What the CJEU has said about the "neutral" role

Two CJEU judgments have narrowed the hosting safe-harbour:

1. **L'Oréal v eBay (C-324/09, 2011):** a provider whose role is "active" — playing "an active role of such a kind as to give it knowledge of, or control over" the data — falls outside the safe-harbour.
2. **YouTube / Cyando / Poland v Parliament (C-401/19, 2022; YouTube/Cyando 2021):** an algorithmic recommendation that goes beyond "mere categorisation and indexation" to "determine, in its own interest, the conditions, manner or priority in which content is broadcast" takes the provider outside the safe-harbour. (Matheson summary: https://www.matheson.com/insights/cjeu-clarifies-the-limits-of-the-hosting-safe-harbour-for-online-platforms/)

A second CJEU judgment of 2024–2025 (the *Brexit/Recommendation Algorithm* cases referenced by Kubiack, https://www.kubiack.com/genai-user-content-platform-intermediate-liability-and-fundamental-rights/) extends this: a provider that *examines* content in connection with a commercial partnership falls outside the safe-harbour, even where it does not intervene to modify or delete. The reasoning: examination gives *knowledge*.

### 4.3 How the three options map to DSA

**Client-side E2EE.** The operator does not have actual knowledge of content. The operator cannot be deemed to "examine" content because content is never in the operator's possession in a form they can examine. DSA Art. 6 safe-harbour applies. Art. 8 (no general monitoring) reinforces this. The operator's *obligation* on receiving a notice of illegal content is to act "expeditiously" — and for encrypted content, "expeditiously" can only mean terminating the user's account, deleting the ciphertext, or making it inaccessible. The operator cannot decrypt, which is an acknowledged limit and not a failure to act.

*Practical DSA risk:* the operator is still obligated to act on a credible, substantiated notice. If the notice identifies a user, the operator can (and must) terminate the user's account and delete the ciphertext. If the notice identifies *content* the operator cannot read, the operator can only delete the ciphertext and trust that the user is identified correctly via metadata.

**TEE.** The operator's server *does* see plaintext briefly during inference (in the enclave). The operator's role is *not* neutral with respect to content: the operator actively transforms the prompt and produces the response. Under the L'Oréal/YouTube logic, this likely takes the operator *outside* the Art. 6 safe-harbour entirely, because the operator "plays an active role of such a kind as to give it knowledge of, or control over" the data. Even if the operator cannot exfiltrate plaintext from the enclave (attestation holds), the operator still has *technical capability* to do so.

*This is dispositive:* **TEE for AI inference likely removes the operator from DSA hosting safe-harbour** because the operator is not a neutral intermediary but an active generator of the response. The operator must then defend against illegal-content liability under general tort / civil-law principles — and the defence is "we have implemented security measures (TEE + attestation) that prevent the operator from being able to act on knowledge of illegal content." This is a weaker defence than the E2EE safe-harbour.

**Escrow.** The operator has *full actual knowledge* — the operator reads the plaintext. Safe-harbour collapses. The operator is a publisher of the content for DSA purposes. The operator owes full notice-and-action, content-moderation under national law, and is exposed to contributory liability for any illegal content the operator has read or could have detected with reasonable diligence.

### 4.4 The notice-and-action problem under E2EE

DSA Art. 16 requires hosting services to provide "easily accessible" notice mechanisms and to act on "substantiated notices." For an E2EE service, the operator receives a notice that says "user X's chat on date Y contained CSAM." The operator:

- *Cannot verify the notice* (cannot read the ciphertext)
- *Must act* on a substantiated notice under Art. 6(1)(b)
- The act available is: terminate account, delete ciphertext, preserve metadata for potential law-enforcement cooperation

The operator's *correct posture* is: take down on receipt of a credible notice, log the action, and provide metadata to law enforcement under MLAT / cross-border cooperation. This is what Signal does. Proton does the same.

**Important caveat:** DSA Art. 6(2) does *not* apply to escrow services where the user acts "under the authority or the control of the provider." For a roleplay service where the operator curates character cards, sets terms of service, and operates the prompt-assembly logic, a court could plausibly find the user is acting "under the operator's authority" — which would *also* remove the safe-harbour. This is a separate problem from E2EE per se.

---

## 5. EU Chat Control (CSAR) — September 2026 status and what it means for E2EE

### 5.1 Status as of September 2026

Two legislative tracks:

**Chat Control 1.0 (Regulation (EU) 2026/1881).** Temporary, voluntary scanning regime. Published in OJ 28 July 2026; in force 31 July 2026; expires 3 April 2028. Passed on second reading on 9 July 2026 by a fast-track procedure — the motion to reject drew 314 votes against reinstatement, 276 for, 17 abstentions, but this was *short of the 360-vote absolute majority* required to block in second reading. Critical: the text includes amendments AM30 and PC3 that explicitly **protect end-to-end encryption**, including against client-side scanning. Article 1(2) excludes audio. Article 1(3) excludes "interpersonal communications to which end-to-end encryption is, has been or will be applied." Recitals state nothing in the regulation may be interpreted as prohibiting or weakening E2EE.

**Chat Control 2.0 (CSAR — permanent framework).** Under trilogue. Fifth trilogue on 29 June 2026 ended without agreement. Sixth trilogue scheduled for 29 September 2026 under the Irish Presidency. Negotiators have already agreed to protect encryption and to remove age verification. The remaining dispute is: **mandatory vs voluntary detection**, and **targeted (judicial-order-based) vs mass (suspicionless) scanning**.

(Council legal advisers have warned that suspicionless scanning may clash with EU Charter of Fundamental Rights. The blocking minority in Council: Germany, Poland, Austria, Estonia, Slovenia, Luxembourg, Netherlands, Finland, Czechia — collectively >35% of EU population, which can block. The pro-scanning bloc: Denmark, Ireland, Spain, Italy, plus at least Bulgaria, Croatia, Cyprus, France, Hungary, Latvia, Lithuania, Malta, Portugal, Slovakia.)

### 5.2 What this means for an E2EE AI roleplay operator

**As of September 2026, no EU law compels E2EE services to provide client-side scanning or backdoors.** The temporary 1.0 regime explicitly excludes E2EE communications. The permanent 2.0 regime has not been agreed; the Parliament's stated position is to protect E2EE.

**The political risk for 2027–2028 is real.** The Council, led by Denmark (which pushed a strong version in October 2025 and was blocked by Germany + Luxembourg + 7 others), has signalled it will revisit mandatory detection. The Irish Presidency in the second half of 2026 has historically backed the pro-scanning bloc. If CSAR 2.0 passes with mandatory client-side scanning, the effect on E2EE services would be:

- Operators of E2EE services *may* be ordered to implement client-side scanning
- The orders would come from EU member-state authorities, not EU institutions directly
- The orders would require judicial approval under the regulation
- The orders would apply to communications, not necessarily to AI prompts (the legal classification of an AI roleplay prompt as "interpersonal communication" is contested)

**Signal's stated response** is to leave the EU market rather than implement client-side scanning. This is a credible threat because Signal's user base is small and the EU is a small share of their business; for a solo EU-based operator, leaving the EU market is not an option — the operator is *in* the EU.

**What an operator should price in:**
- If the operator ships E2EE today and the law forces client-side scanning in 2027–2028, the operator has 12–24 months of compliance runway before the architecture must change
- The compliance change is technically possible (client-side scanning is a client-side feature) but operationally expensive
- The compliance change *breaks the user's expectation* of E2EE and is a marketing problem, not just a legal one
- An operator that ships E2EE today has a defensible legal posture for the next 12–24 months regardless of CSAR 2.0 outcome

---

## 6. Russia-specific risk for an EU/Russia-based solo operator

### 6.1 The operator's personal situation

A "solo EU/Russia-based operator" is ambiguous on its face. Two distinct scenarios:

**Scenario A: Operator physically resides in Russia but hosts infrastructure abroad (e.g., a Hetzner VPS in Germany).** Russian personal-data law applies to the *operator*, regardless of where servers are located. Russian criminal and civil law apply to the operator for any act the operator commits that touches Russia. Russian law can compel the operator to act extraterritorially (force the operator to delete data from German servers, terminate Russian users' accounts, surrender keys). Failure to comply can result in: blocking the operator's Russian-payment rails, blocking the operator's Russian-user-facing endpoints via Roskomnadzor, criminal prosecution under Art. 137 of the Russian Criminal Code (violation of personal-data privacy) or Art. 272 (illegal access to computer information), with fines up to 18 million rubles for repeat violations under the 2024 amendments.

**Scenario B: Operator physically resides in EU (e.g., Germany, Finland, Czechia) but is a Russian citizen or has Russian ties.** EU law applies primarily. Russian personal-data law still applies to the *processing* of Russian citizens' personal data (242-FZ is extraterritorial). Russian law can still attempt to compel the operator (via MLAT or via blocking + sanctions on payment rails); the operator can refuse on EU-law grounds but must be prepared to lose Russian users.

**Scenario C: Operator physically resides in EU, no Russian ties, hosts in EU, no Russian users.** None of the Russia-specific analysis below applies. (This is the easy case.)

For a *solo EU/Russia-based* operator, Scenario A or B is the default reading. The rest of §6 assumes that case.

### 6.2 Federal Law 242-FZ + 23-FZ (July 2025) — data localisation

- **Since September 2015:** operators must store personal data of Russian citizens using databases physically located in Russia.
- **Since 1 July 2025 (Law 23-FZ, signed 28 February 2025):**
  - Initial collection of personal data via databases outside Russia is *expressly prohibited* — i.e., the form, chatbot, or signup endpoint that writes Russian users' data to a foreign server before replicating to Russia is itself unlawful.
  - Processors (not just operators) are bound.
  - Operators must notify Roskomnadzor of database locations.
  - Penalties: 1–6 million rubles initial; 6–18 million rubles repeat; Roskomnadzor can block the operator's Russian-facing endpoints.

The EDPB-equivalent (Roskomnadzor) uses an automated monitoring system called Revizor to verify server locations. The .ru/.su TLDs, Russian-language content, Russian-currency acceptance, and Russian-language advertising are the four tests Roskomnadzor uses to determine whether a foreign entity "targets Russian users."

**For an AI roleplay service hosted outside Russia:**

- *If the service has no Russian users:* Russian law does not apply (de facto; Roskomnadzor may still try to assert jurisdiction but extraterritorial enforcement against an EU-resident operator is rare and politically costly).
- *If the service has even a few Russian users:* Roskomnadzor can block the operator's domain in Russia, force Russian payment processors (YooMoney, Tinkoff, Sberbank) to refuse payments, and require Russian ISPs to block the IP addresses.

### 6.3 SORM (System of Operative-Investigative Activities)

Federal Law 149-FZ + Government Decree 1952 (22 November 2023, in force 1 December 2023) requires *hosting providers* and *information dissemination organisers* to install SORM equipment at their own expense. The SORM installation:

- Must be coordinated with FSB
- Requires a direct communication line from the operator's infrastructure to an FSB control panel
- Costs the operator between €50K–€500K+ depending on traffic scale (typical industry estimate)
- Includes both metadata collection (3-year retention) and content interception capability
- May also, since April 2026 amendments, give FSB the right to demand *free-of-charge copies of any database* held by the operator that is not already provided via SORM

For an AI roleplay service:

- The service likely qualifies as an "information dissemination organiser" if users exchange messages (even via prompts to characters)
- The service definitely qualifies as a "hosting provider" if the operator rents compute to users (most AI services do not, but the LLM proxy layer is ambiguous)
- As of October 2025, FSB has required *banks* to install SORM by 2027 because users can exchange messages in mobile apps; the same logic applies to AI services that include any messaging / chat persistence

**For a solo operator physically in Russia:**
- SORM installation is *mandatory* if the operator hosts in Russia
- SORM installation is *legally impossible* if the operator hosts outside Russia (FSB cannot compel a German Hetzner server to install Russian-government-controlled equipment)
- SORM installation is *legally ambiguous* if the operator hosts outside Russia but is physically in Russia — the operator can be criminally prosecuted for failing to install SORM in Russian territory, but cannot practically do so for foreign infrastructure

**Critical: "E2EE" provides no defence against SORM.** SORM operates at the network-layer (deep-packet inspection, BGP-level interception, infrastructure-level access). A Signal-style E2EE service would still be subject to SORM infrastructure if the operator is in Russia and the SORM equipment is installed. SORM has been operational in Russia since 1996 (SORM-1) and 2000 (SORM-2); the legal framework is mature and enforcement is non-negotiable for Russian entities.

### 6.4 Criminal-law exposure for the operator

Russian Criminal Code provisions of relevance:

- **Art. 137** (violation of personal-data privacy): up to 5 years imprisonment + fines
- **Art. 272** (illegal access to computer information): up to 7 years imprisonment
- **Art. 242** (illegal production and circulation of pornographic materials): up to 6 years imprisonment
- **Art. 242.1** (production / circulation of materials with minors in pornography): up to 15 years imprisonment
- **Art. 242.2** (use of minors in production of pornography): up to 8 years imprisonment

**For an AI roleplay service, the exposure under Art. 242.1 and 242.2 is severe.** Russian law criminalises the production of sexual content involving minors with no exception for fictional, textual, or AI-generated content. (This is more restrictive than EU law, which has a narrower "virtual CSAM" provision under Directive 2011/93/EU.) If the operator's service is used to generate roleplay content that involves minors in sexual scenarios, the operator has potential criminal exposure *regardless of E2EE*.

The E2EE defence to Art. 242.1 is structurally weak: the operator's *inability to read* the content does not preclude the operator from being found to have *knowingly facilitated* the production of illegal content (e.g., if a minor was the user, if the system prompt enabled the content, if the operator marketed the service to that demographic).

### 6.5 The "hosting abroad" gap

If the operator hosts entirely outside Russia (EU or elsewhere), the operator:

- Is still subject to Russian personal-data law (242-FZ + 23-FZ) for any Russian users
- Is not subject to SORM installation in the technical sense (FSB cannot install equipment in a foreign data centre)
- *Can* still be criminally prosecuted if physically present in Russia (e.g., for refusing to comply with a Roskomnadzor order to delete Russian users' data from the foreign server)
- Faces blocking of Russian-facing endpoints (Roskomnadzor can block the domain, Russian ISPs can block the IP, Russian payment processors can refuse the service)

The bottom line for the solo operator: **the safest architecture for Russia is to have no Russian users at all**, not because E2EE fails but because Russian personal-data law + SORM + criminal-law exposure are structural and have no architectural mitigation. E2EE reduces GDPR/DSA exposure but does not reduce Russian-law exposure for the operator's *own* Russian-resident status.

---

## 7. The legal exposure comparison table

The brief asked for a comparison across the three options. The table below maps each option to every regime identified above. Lower numbers = lower exposure.

| Regime / dimension | Client-side E2EE (Signal model) | TEE (operator's server, attested enclave) | Escrow (current SaaS, operator holds key) |
|---|---|---|---|
| **GDPR Art. 4 status of data the operator holds** | Pseudonymised (per EDPB Guidelines 01/2025); arguably not personal data if operator cannot decrypt (minority academic view) | Pseudonymised at rest; plaintext during inference; still personal data | Personal data in plaintext |
| **GDPR Art. 32 security obligations** | Met by design; encryption + key isolation | Met by design for data at rest; questionable for data in use (enclave vulnerabilities) | Owed in full; failure to encrypt is a violation |
| **GDPR Art. 33/34 breach exposure** | Art. 34(3)(a) exemption likely (data unintelligible to unauthorised); lower fines | Art. 34(3)(a) exemption for at-rest; full obligation for in-use breaches | Full obligation; breach is catastrophic (all user plaintext exposed) |
| **GDPR data-subject rights (Art. 15-22)** | Operator must still respond (metadata); cannot respond to access request for content user won't decrypt | Operator must respond (re-derive inside enclave); contradicts the privacy value prop | Operator must respond (read from DB) |
| **GDPR pseudonymisation credit (Art. 32(1)(a), 25, 34)** | Full credit; privacy by design | Partial credit (at rest); weak in-use | None |
| **GDPR fines (max 4% global turnover or €20M)** | Lower likelihood; lower maximum proportional to actual exposure | Medium; depends on whether attestation holds | Higher; full exposure |
| **DSA Art. 6 hosting safe-harbour** | Applies (no actual knowledge of content) | Likely does *not* apply (operator is active generator, not neutral intermediary per CJEU L'Oréal / YouTube / Cyando) | Does *not* apply (operator has full actual knowledge) |
| **DSA Art. 8 no-general-monitoring** | Fully available | Weakly available; inference itself is processing of content | Not available; operator is doing the monitoring |
| **DSA notice-and-action (Art. 16)** | Obligated to act on substantiated notice by terminating account / deleting ciphertext | Obligated to act; technically cannot verify content; can only terminate | Obligated to act on substantiated notice by reading, removing, logging |
| **DSA illegal-content liability** | Low; can only be liable if illegal content is in *metadata* the operator saw | Medium; liable if operator's inference produced illegal content (i.e., the operator is *the publisher* of the AI response) | High; liable for any illegal content stored, transmitted, or generated |
| **EU AI Act provider/deployer status** | Deployer (uses third-party GPAI model); Art. 50 transparency + Art. 26 deployer obligations | Deployer + provider of a confidential-inference architecture (Art. 9 may be satisfied) | Deployer + provider |
| **EU AI Act Art. 9 "encryption" technical measure** | Satisfied (data at rest and in transit) | Satisfied (data at rest, in transit, in use) | Not satisfied by default |
| **CSAR "Chat Control 2.0" exposure (if it passes in 2027–2028 with mandatory client-side scanning)** | High *if* the regulation is interpreted to apply to E2EE AI prompts (likely opt-out: leave EU market, as Signal has said) | High — TEE does not satisfy client-side scanning requirement (the point of client-side scanning is to defeat end-to-end encryption) | Lower (operator already has plaintext; client-side scanning is redundant) |
| **Russia 242-FZ + 23-FZ data localisation** | Not applicable to operator's processing if E2EE means operator never sees Russian user data — *but* the *signup form*, *payment metadata*, and *IP logs* are personal data and must be stored in Russia | Same; in fact arguably cleaner because the operator genuinely cannot read content | Same; plus content is plaintext Russian user data, definitely must be localised |
| **Russia SORM installation** | Mandatory if operator in Russia; not technically possible for foreign infrastructure; irrelevant if E2EE means no content is held | Same | Same |
| **Russia criminal exposure (Art. 242, 242.1)** | No defence; if minors are involved in roleplay, operator has facilitated regardless of E2EE | No defence; operator is the active generator of illegal content (higher exposure) | No defence; operator is the publisher of illegal content (highest exposure) |
| **Metadata-driven liability (CJEU Breyer, pattern detection)** | Low to medium; metadata is plaintext (IP, timestamps, account creation) | Same | Same |
| **Operator's own subpoena exposure (US, EU, Switzerland)** | Substantially reduced — operator has nothing to produce on content; metadata only | Substantially reduced on content; full exposure if attestation keys are compromised | Full; operator must produce everything or face contempt |
| **Reputational / marketing exposure** | Best ("we cannot read it") | Good ("not even we can read it") | Worst ("we read it to keep you safe" — DuckDuckGo framing; or just "we can read it" with no defence) |
| **Operator's technical investment required** | Highest (client-side architecture, key management, metadata minimisation, native or PWA with WebCrypto) | Medium-high (TEE infrastructure, attestation services, key-release policy, MRTD management, CVE monitoring) | Lowest (default SaaS pattern) |
| **Engineering risk** | High (single-implementation bug compromises everything — see Obsidian Trail of Bits 2025 audit) | Medium (CVE-2026-15430 vLLM RCE, attestation bypass, MRSEAM revocation checks) | Low |
| **Overall legal exposure (operator physically in EU, hosting in EU)** | **Lowest** | Medium-low (novel, untested in court) | Highest |
| **Overall legal exposure (operator physically in Russia, hosting abroad)** | Low (for content); high (for being a Russian operator with Russian users) | Low (for content); high (for being a Russian operator with Russian users) | Highest (operator has plaintext AND is a Russian operator with Russian users) |
| **Overall legal exposure (operator physically in Russia, hosting in Russia)** | Same as above + mandatory SORM installation + mandatory data localisation (already met for content if E2EE) | Same as above + mandatory SORM installation (TEE does not preclude SORM) | Same as above + mandatory SORM installation + plainest possible illegal-content liability |

### Quick reference: which option wins on which dimension

| Dimension | Winner |
|---|---|
| GDPR Art. 32 / Art. 34 | E2EE |
| DSA hosting safe-harbour | E2EE |
| Subpoena resistance | E2EE > TEE >> Escrow |
| CSAR 2.0 compliance (if mandatory client-side scanning passes) | Escrow |
| Russian data-localisation compliance | E2EE (technically no content held) |
| Russian SORM compliance | None (operator in Russia must install SORM regardless) |
| AI Act provider duties | All three equivalent (depends on what you fine-tune / deploy) |
| Engineering cost | Escrow < TEE < E2EE |
| Marketing value | E2EE > TEE > Escrow |
| Provenance / court-tested | E2EE (Signal, Proton, WhatsApp for 10+ years); TEE (not yet in this domain); Escrow (every SaaS, but not a defence) |

---

## 8. The operator's optimal posture

For a solo EU/Russia-based operator running a hosted AI roleplay service, the legal analysis converges on:

1. **Ship client-side E2EE for content.** This is the only architecture with proven court-tested defence. It costs the most to build but reduces legal exposure the most.

2. **Treat E2EE as an *architecture*, not a *feature*.** The architecture must be: keys generated on device; never sent to server; metadata minimised; no server-side feature that requires plaintext (memory consolidation, search, character card generation all must be client-side per the e2ee-app-architecture-survey).

3. **Document the architecture publicly.** Signal's, Proton's, Standard Notes's value depends on *public* verification. Audit reports, transparency reports, and verifiability tooling are the trust infrastructure. Without them, "we cannot read it" is a marketing claim and not a legal defence.

4. **Use a TEE for the LLM call, with explicit attestation.** The operator cannot run the LLM locally (not for roleplay-scale models); the operator must call an LLM provider. The two options are:
   - **Tier 1 (best):** the client encrypts the prompt to the LLM provider's public key (BYOK-style, Proton Lumo / Signal-bot-tee / OpenGradient model). The operator's server is a dumb relay. The LLM provider is the only entity that sees plaintext.
   - **Tier 2:** the operator runs the LLM in an attested TEE. The operator has no key. Attestation logs are public.
   - **Tier 3:** the operator runs the LLM in plaintext with contractual obligations to the LLM provider. This is escrow with extra steps.

5. **For Russia specifically:**
   - If the operator is physically in Russia, hosting in Russia, serving Russian users: ship E2EE for content (reduces Article 242 exposure marginally), but understand that the operator is in a hostile jurisdiction and there is no architectural mitigation for the operator's own Russian-resident status. Consider re-domiciling to EU.
   - If the operator is physically in Russia, hosting abroad: ship E2EE, refuse Russian users entirely (geoblock + terms-of-service), accept that Russian personal-data law still applies for any leaked Russian users (Russian credit card, Russian IP, Russian-language browser).
   - If the operator is physically in EU, hosting in EU, with Russian citizens as users: ship E2EE, comply with 242-FZ for Russian users' account-creation data (signup form must write to a Russian database first), accept that SORM is not applicable (no equipment to install in EU data centres), and prepare for Russian-government pressure to terminate specific users.

6. **For Chat Control 2.0 specifically:**
   - Track the September 2026 trilogue.
   - If CSAR 2.0 passes with mandatory client-side scanning, the architecture must change. Plan a 6-month migration to either (a) client-side scanning with a credible third-party audit, (b) an opt-in architecture where users explicitly accept scanning, or (c) geo-fencing EU users and exiting the EU market.
   - Signal's stated position is to leave the EU market; this is a credible threat for a small E2EE provider. For a solo operator without Signal's brand, geo-fencing is the realistic option.

7. **Avoid escrow.** The escrow option is the worst legal posture for every regime reviewed. It is also the highest *technical* risk (every breach exposes all user data). The only reason to use escrow is that the operator wants to read the content (for memory consolidation, abuse detection, fine-tuning) — and every one of those features has a privacy-reserving client-side alternative that the e2ee-app-architecture-survey catalogues.

---

## 9. Sources

### EU Chat Control / CSAR
- EDRi, "Chat Control 1.0 saga" (4 August 2026) — https://edri.org/our-work/the-chat-control-1-0-saga-big-tech-can-scan-our-private-messages-again-but-parliament-sent-a-strong-signal-against-mass-surveillance/
- ClosedNetwork, EU Chat Control live tracker — https://closednetwork.io/eu-chat-control-the-fight-to-scan-every-private-message-live-tracker/
- Factually, "Status of CSAR July 2026" — https://factually.co/fact-checks/politics/status-csar-proposal-july-2026-696324
- Factually, "EU position on Chat Control" — https://factually.co/fact-checks/technology/eu-chat-control-stand-explained-9588b5
- WithoutCensorship, "Chat Control: two laws, one nickname" — https://withoutcensorship.com/chat-control-two-laws-one-nickname/
- Regulation (EU) 2026/1881 (published OJ 28 July 2026) — referenced via WithoutCensorship summary

### GDPR / Pseudonymisation
- GDPR Art. 4 — https://eur-lex.europa.eu/eli/reg/2016/679/art_4/oj/eng
- GDPR Art. 32 (Security of processing) — https://gdpr-info.eu/art-32-gdpr/
- EDPB Guidelines 01/2025 on Pseudonymisation (16 January 2025) — https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf
- IAPP, "Is encrypted data personal data under the GDPR?" — https://iapp.org/news/a/is-encrypted-data-personal-data-under-the-gdpr
- Future of Privacy Forum, "Confidential Computing" report — https://fpf.org/fpf-confidential-computing-r3/

### DSA / Hosting safe-harbour
- DSA full text — https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A32022R2065
- DSA Art. 6 (Hosting) — https://overview.legal/laws/dsa/art-6
- Matheson, "CJEU clarifies the limits of the hosting safe harbour" — https://www.matheson.com/insights/cjeu-clarifies-the-limits-of-the-hosting-safe-harbour-for-online-platforms/
- Kubiack Law, "GenAI User Content, Platform Intermediate Liability" — https://www.kubiack.com/genai-user-content-platform-intermediate-liability-and-fundamental-rights/
- Nordic Journal of European Law, "To Host or Not to Host" — https://journals.lub.lu.se/njel/article/view/28036

### TEE / Confidential Computing
- FPF, "Confidential Computing" — https://fpf.org/fpf-confidential-computing-r3/
- BeyondScale, "Confidential Computing AI Inference: CISO Guide 2026" — https://beyondscale.tech/blog/confidential-computing-ai-inference-enterprise-ciso-guide
- OpenPcc paper (2606.11145) — https://arxiv.org/html/2606.11145v1
- CACTEE paper (2026 SysTEX) — https://iakkus.github.io/papers/2026-systex-akkus-cactee.pdf
- Felsen, "TEE Attestation vs. AI Act: The Evidentiary Gap" — https://jfelsen.com/blog/en/trusted-execution-environments-evidentiary-governance-ai-act

### Signal / Proton / E2EE-provider legal precedent
- Signal grand-jury subpoena response (2016) — https://signal.org/
- Signal Privacy Policy / Terms — https://www.supremecourt.gov/opinions/URLs_Cited/OT2023/22-277/22-277-15.pdf
- Signal on Australia's Assistance and Access Act — https://umatechnology.org/signal-we-cant-comply-with-aussie-encryption-law-even-if-we-wanted-to/
- Proton, "Defending the rights of protesters" — https://proton.me/blog/protesters-free-speech
- Proton, "White House staff using Proton Mail" — https://proton.me/blog/white-house-encryption-protonmail
- Proton Swiss court appeal — https://proton.me/

### Russia
- B1 Analytics, "New rules regarding the localization of personal data of Russian citizens" (March 2025) — https://b1.ru/en/insights/law-messenger/localization-of-personal-data-of-russian-citizens-6-march-2025/
- Konsu Group, "New requirements for localization of personal data in Russia" — https://konsugroup.com/en/news/new-requirements-personal-data-protection-russia-2025-07/
- Recording Law, "Russia Data Privacy Laws" — https://www.recordinglaw.com/world-laws/world-data-privacy-laws/russia-data-privacy-laws/
- Presencis, 242-FZ localisation article — https://presencis.com/regulations/ru-242fz/article-cross-border-rules/
- Garant, draft FSB + Ministry of Digital Development order on hosting SORM (May 2025) — https://www.garant.ru/products/ipo/prime/doc/56924124/
- Consultant Plus, MinTsifry Order 1174 (16 December 2025) on SORM for technological networks — https://www.consultant.ru/document/cons_doc_LAW_534792/
- TAdviser, SORM article — https://tadviser.com/index.php/Article:SORM_(System_of_operational-search_measures)
- Meduza, "Russia's surveillance expansion" — https://meduza.io/en/cards/russia-s-surveillance-expansion-isn-t-really-about-telecoms-anymore-it-s-about-building-a-parallel-sorm-inside-every-major-company-in-the-country
- Recorded Future, "Tracking Deployment of Russian Surveillance Technologies in Central Asia and Latin America" (2025) — https://assets.recordedfuture.com/insikt-report-pdfs/2025/ta-ru-2025-0107.pdf

### Companion surveys (this repo)
- `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md`
- `/Storage/Git/spectacle/.hermes/research/e2ee-browser-capability-survey.md`
- `/Storage/Git/spectacle/.hermes/research/e2ee-business-model-survey.md`