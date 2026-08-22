import { UserButton } from "@clerk/nextjs";

export default function Page() {
  return (
    <main>
      <h1>Dashboard</h1>
      <UserButton />
    </main>
  );
}
