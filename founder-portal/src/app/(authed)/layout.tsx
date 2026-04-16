import { redirect } from "next/navigation";
import { getFounder } from "@/lib/auth";
import Nav from "@/components/Nav";

export default async function AuthedLayout({ children }: { children: React.ReactNode }) {
  const founder = await getFounder();
  if (!founder) {
    redirect("/login");
  }

  return (
    <>
      <Nav
        founder={{
          name: founder.name,
          username: founder.username,
          organizationSlug: founder.organization.slug,
        }}
      />
      {children}
    </>
  );
}
