# Little Legend — legal and privacy launch checklist (DRAFT)

**Not legal advice. Do not publish as final terms or enable child-photo upload until reviewed by qualified counsel and the actual service operator.**

## Documents to publish before photo processing

1. **Terms of Service**: legal entity, address/contact, eligibility, order scope, pricing/refunds, IP rights, content restrictions, service limitations, disputes and governing law.
2. **Privacy Notice**: controller identity, privacy contact, categories of children's data, legal bases, purposes, recipients and subprocessors (including image-generation providers), locations and international transfers, retention/deletion periods, security, data subject rights and complaint channel.
3. **Separate Parental Photo Consent**: optional, unticked by default; plain-language purposes and consequences; records of policy version/time/owner; simple withdrawal; no unrelated marketing consent bundled in.
4. **Processor agreements and technical controls**: verify providers' data retention, model training opt-outs, subcontractors, transfers, deletion capability, encryption, incident handling and access logging.
5. **Parental authority verification**: declaration alone is not proof of authority; define proportionate verification and escalation for disputed custody/rights.
6. **Retention/deletion operations**: implement real purge of originals, derivatives, caches, backups and processor copies under a documented schedule. Consent withdrawal must stop further processing and trigger applicable deletion workflows.
7. **Age and jurisdictions**: adapt to Ukraine and actual markets (EU, US etc.). For EU children, check the relevant national threshold and whether GDPR Article 8 applies to the service; US COPPA may also apply depending on audience and collection.
8. **Prohibited uses**: unlawful or abusive content, uploading others' photos without authorization, non-consensual publication, impersonation, exploitation or sexualization of minors.

## Accurate commitments

- Never claim “we do not share with third parties” if image-generation APIs or hosting subprocessors receive images.
- Do not promise immediate deletion of all copies unless verified across backups and subprocessors.
- Do not imply consent alone makes biometric recognition lawful; avoid face identification/embeddings unless separately assessed.
- Avoid guaranteeing perfect likeness.
- Never train the operator's own models on child photos without separate permission; verify external processor terms.

## Engineering launch gates

Current implementation: owner-scoped acceptance and withdrawal of versioned declarations. **No image upload, image storage, model invocation, automatic deletion, parent verification or provider DPA is implemented by this change.** These must be separately delivered and audited before production launch.

Sources:
- https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng
- https://commission.europa.eu/law/law-topic/data-protection/information-individuals_en
- https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/legal-grounds-processing-data_en
