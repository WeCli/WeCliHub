import { ProfilePage } from "@/components/flowhub/profile-page";

export default async function Page({ params }: { params: Promise<{ login: string }> }) {
  const { login } = await params;
  return <ProfilePage login={login} />;
}
