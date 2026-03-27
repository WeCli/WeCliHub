import { spawnSync } from "node:child_process";

export function yamlToLayoutData(yamlContent: string):
  | { available: false; error: string }
  | { available: true; data?: unknown; error?: string } {
  const script = `import base64\nimport json\nimport sys\n\nraw = sys.stdin.read()\ntry:\n    yaml_text = base64.b64decode(raw.encode('ascii')).decode('utf-8')\nexcept Exception:\n    print(json.dumps({'available': False, 'error': 'Invalid input'}))\n    raise SystemExit(0)\n\ntry:\n    from mcp_oasis import _yaml_to_layout_data\nexcept Exception:\n    print(json.dumps({'available': False, 'error': 'Layout engine not available'}))\n    raise SystemExit(0)\n\ntry:\n    data = _yaml_to_layout_data(yaml_text)\n    print(json.dumps({'available': True, 'data': data}, ensure_ascii=False))\nexcept Exception as e:\n    print(json.dumps({'available': True, 'error': f'Layout conversion failed: {e}'}))\n`;

  const encoded = Buffer.from(yamlContent, "utf-8").toString("base64");
  const process = spawnSync("python3", ["-c", script], {
    input: encoded,
    encoding: "utf-8",
    timeout: 6000
  });

  if (process.error) {
    return { available: false, error: "Layout engine not available" };
  }

  const stdout = process.stdout?.trim();
  if (!stdout) {
    return { available: false, error: "Layout engine not available" };
  }

  try {
    const parsed = JSON.parse(stdout) as { available: boolean; data?: unknown; error?: string };
    if (!parsed.available) {
      return { available: false, error: parsed.error || "Layout engine not available" };
    }
    return { available: true, data: parsed.data, error: parsed.error };
  } catch {
    return { available: false, error: "Layout engine not available" };
  }
}
