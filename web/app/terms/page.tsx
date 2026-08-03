import { LegalDocument, LegalSection } from "@/components/legal-document";

export default function TermsPage() {
  return (
    <LegalDocument title="Terms of Service">
      <p>These draft terms apply only to invited private-alpha testers and await legal review.</p>
      <LegalSection title="Eligibility and accounts">
        <p>
          Access is personal, limited to approved testers, and may be closed or withdrawn.
          Keep credentials secure and do not share sessions or access another user&apos;s data.
        </p>
      </LegalSection>
      <LegalSection title="Uploaded match videos">
        <p>
          You retain ownership of uploads and are responsible for recording and upload
          permission from players, spectators, venues, and other rights holders. Do not
          upload unlawful, harmful, or confidential material.
        </p>
      </LegalSection>
      <LegalSection title="Experimental service">
        <p>
          Court4 is an alpha product. Results may be incomplete, delayed, unsuitable, or
          incorrect. There is no promise of automatic recording, point analysis,
          coaching, partner discounts, store availability, uninterrupted operation, or
          permanent storage.
        </p>
      </LegalSection>
      <LegalSection title="Acceptable use and security">
        <p>
          Do not probe internal routes, bypass authorization, disrupt the service, upload
          malware, or use results to harm or unfairly evaluate another person. Report
          suspected compromise through the invitation contact.
        </p>
      </LegalSection>
      <LegalSection title="Suspension, deletion, and changes">
        <p>
          Court4 may suspend alpha access for safety, security, or operational reasons.
          Account and content deletion requests are processed manually. Material changes
          will be communicated to active testers before continued use is requested.
        </p>
      </LegalSection>
      <LegalSection title="Contact">
        <p>
          Use the operator contact supplied with your invitation for support, security,
          deletion, or terms questions. Permanent public contacts are required before
          broader availability.
        </p>
      </LegalSection>
    </LegalDocument>
  );
}
