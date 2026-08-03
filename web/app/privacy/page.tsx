import { LegalDocument, LegalSection } from "@/components/legal-document";

export default function PrivacyPage() {
  return (
    <LegalDocument title="Privacy Policy">
      <p>This private-alpha draft is pending legal and operational review.</p>
      <LegalSection title="Data we process">
        <p>
          Court4 processes account details, security-session records, and match videos
          you upload. Video may include players, spectators, voices, venue signage, and
          other information visible or audible in the recording.
        </p>
      </LegalSection>
      <LegalSection title="Permission and ownership">
        <p>
          You retain ownership of uploaded content. You must have the right to record
          and upload it and obtain any required permission from visible or audible
          participants. Court4 receives only the limited permission needed to provide
          the private-alpha service.
        </p>
      </LegalSection>
      <LegalSection title="Processing and current limitations">
        <p>
          Court4 may inspect quality, detect court geometry, discover player candidates,
          and generate movement or positioning results. Alpha analytics are experimental
          and are not professional advice.
        </p>
      </LegalSection>
      <LegalSection title="Storage, retention, and deletion">
        <p>
          The alpha uses controlled application and database storage. A complete
          automated retention/deletion engine is not yet available. Use the invitation
          contact to request manual deletion of an account or uploaded content; backup
          and security constraints will be disclosed when the request is confirmed.
        </p>
      </LegalSection>
      <LegalSection title="Model improvement and analytics">
        <p>
          Uploading does not consent to model training. Optional model-improvement use
          requires a separate informed opt-in. Product analytics are currently limited;
          this draft does not authorize undisclosed tracking.
        </p>
      </LegalSection>
      <LegalSection title="Service providers and security">
        <p>
          Infrastructure, database, and transactional-email providers may process the
          minimum data needed for their services. Court4 uses verification, password
          hashing, scoped access, and managed sessions, but cannot guarantee absolute
          security.
        </p>
      </LegalSection>
      <LegalSection title="Contact">
        <p>
          Send privacy and deletion requests through the contact supplied with your
          tester invitation. A permanent public privacy contact is required before a
          wider release.
        </p>
      </LegalSection>
    </LegalDocument>
  );
}
