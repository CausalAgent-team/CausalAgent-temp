import { markRaw } from 'vue'
import type { CausalGraphData } from '../types/domain'

interface GraphInstance {
  on: (event: string, callback: () => void) => void
  setOptions: (options: Record<string, unknown>) => void
  destroy: () => void
}

interface VisNetworkModule {
  Network: new (
    container: HTMLElement,
    data: { nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>> },
    options: Record<string, unknown>,
  ) => GraphInstance
}

const graphOptions: Record<string, unknown> = {
  layout: { hierarchical: { enabled: false } },
  edges: {
    arrows: { to: { enabled: true, scaleFactor: 1, type: 'arrow' } },
    color: '#848484',
    font: { size: 12 },
    smooth: { enabled: true, type: 'dynamic' },
  },
  nodes: { shape: 'box', size: 30, font: { size: 14, color: '#333' }, borderWidth: 2 },
  interaction: { dragNodes: true, dragView: true, zoomView: true },
  physics: {
    enabled: true,
    barnesHut: {
      gravitationalConstant: -2000,
      centralGravity: 0.3,
      springLength: 95,
      springConstant: 0.04,
      damping: 0.09,
      avoidOverlap: 0.1,
    },
    solver: 'barnesHut',
    stabilization: { iterations: 1000 },
  },
}

export async function mountCausalGraph(container: HTMLElement, graph: CausalGraphData): Promise<() => void> {
  const module = await import('vis-network/standalone') as unknown as VisNetworkModule
  const network = markRaw(new module.Network(container, { nodes: graph.nodes, edges: graph.edges }, graphOptions))
  network.on('stabilizationIterationsDone', () => network.setOptions({ physics: { enabled: false } }))
  return () => network.destroy()
}
