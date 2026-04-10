import { WorkflowDetailPage } from "@/components/clawcrosshub/workflow-detail-page";

export default async function WorkflowPage({
  params
}: {
  params: Promise<{ workflowId: string }>;
}) {
  const { workflowId } = await params;
  return <WorkflowDetailPage workflowId={workflowId} />;
}
