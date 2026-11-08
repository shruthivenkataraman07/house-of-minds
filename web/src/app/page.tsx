import Dashboard from "@/components/Dashboard";

/** Static shell; all data is fetched from the FastAPI service (/api/v1). */
export default function Home() {
  return <Dashboard />;
}
