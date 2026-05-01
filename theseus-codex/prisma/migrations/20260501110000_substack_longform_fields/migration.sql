-- Long-form outbound publishing fields for Substack email-to-post drafts.
-- X posts continue to use "body"; Substack uses "subject" for the email
-- subject/title, "body" for the subtitle, and "markdownBody" for the post.
ALTER TABLE "SocialPost"
  ADD COLUMN IF NOT EXISTS "markdownBody" TEXT,
  ADD COLUMN IF NOT EXISTS "subject" TEXT;
