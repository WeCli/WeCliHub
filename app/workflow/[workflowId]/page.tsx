import { WorkflowDetailPage } from "@/components/flowhub/workflow-detail-page";

export default async function WorkflowPage({
  params
}: {
  params: Promise<{ workflowId: string }>;
}) {
  const { workflowId } = await params;
  return <WorkflowDetailPage workflowId={workflowId} />;
}
