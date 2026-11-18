
import { useEffect, useState } from 'react'
import {
  Activity,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  CircleAlert,
  FileText,
  GitBranch,
  Package,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  Play,
  ClipboardList,
  Truck,
} from 'lucide-react'

const API = 'http://127.0.0.1:8000/api'

type Summary = {
  dataset: string
  records: number
}

type Supplier = {
  supplier_id?: string
  supplier_name?: string
  ranking_score?: number
  recommendation_source?: string
  reference_price?: number | string
  [key: string]: unknown
}

type RequirementResult = {
  requirement_id: string
  item_code?: string | null
  plant?: string | null
  total_quantity?: number
  line_count?: number
  total_value?: number | null
  unit_price?: number | null
  route?: string | null
  decision?: string | null
  action?: string | null
  policy_rule_id?: string | null
  decision_reason?: string | null
  valuation_status?: string
  valuation_source?: string
  contract_allocation_status?: string
  contract_id?: string | null
  supplier_recommendation_status?: string
  supplier_count_returned?: number
  recommended_suppliers?: Supplier[]
  is_new_item?: boolean
  is_emergency?: boolean
}

type InvalidLine = {
  pr_no?: string
  pr_line?: string
  item_code?: string | null
  plant?: string
  validation_errors?: string[]
  [key: string]: unknown
}

type ProcessResponse = {
  success: boolean
  message: string
  request_source: string
  policy?: {
    version: string
    effective_date: string
  }
  summary: {
    total_input_lines: number
    valid_lines: number
    invalid_lines: number
    clubbed_lines: number
    consolidated_requirements: number
    requirements_processed: number
    route_summary: Record<string, number>
    decision_summary: Record<string, number>
  }
  invalid_lines: InvalidLine[]
  requirement_results: RequirementResult[]
  contract_allocations: Record<string, unknown>[]
  contract_balances: Record<string, unknown>[]
  final_line_results: Record<string, unknown>[]
  limitations?: string[]
}

const labels: Record<string, string> = {
  item_master: 'Item master',
  supplier_master: 'Supplier master',
  po_history: 'Purchase history',
  plants: 'Plants',
  contract_register: 'Contract register',
  contract_lines: 'Contract lines',
  sample_pr_batch: 'Sample PR batch',
}

function formatCurrency(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return '—'
  }

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(Number(value))
}

function formatLabel(value?: string | null) {
  if (!value) return 'Not available'

  return value
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function App() {
  const [health, setHealth] = useState('Checking')
  const [summary, setSummary] = useState<Summary[]>([])
  const [policy, setPolicy] = useState('Loading')
  const [busy, setBusy] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [result, setResult] = useState<ProcessResponse | null>(null)
  const [activeTab, setActiveTab] = useState<'requirements' | 'invalid'>('requirements')

  async function refresh() {
    try {
      const [healthResponse, summaryResponse, policyResponse] = await Promise.all([
        fetch(`${API}/health`),
        fetch(`${API}/data/summary`),
        fetch(`${API}/policies`),
      ])

      setHealth(healthResponse.ok ? 'Connected' : 'Unavailable')

      if (summaryResponse.ok) {
        setSummary(await summaryResponse.json())
      }

      if (policyResponse.ok) {
        const policies = await policyResponse.json()
        const activePolicy = policies.find(
          (item: { status: string }) => item.status === 'active',
        )
        setPolicy(activePolicy?.version ?? 'Not seeded')
      } else {
        setPolicy('Unavailable')
      }
    } catch {
      setHealth('API offline')
      setPolicy('Unavailable')
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function importData() {
    setBusy(true)
    setMessage('')
    setError('')

    try {
      const response = await fetch(`${API}/data/import`, {
        method: 'POST',
      })

      const body = await response.json()

      if (!response.ok) {
        throw new Error(body.detail ?? 'Import failed')
      }

      setMessage(
        `Imported ${body.total_records} records across ${Object.keys(body.counts).length} datasets.`,
      )

      setResult(null)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not import data')
    } finally {
      setBusy(false)
    }
  }

  async function processBatch() {
    setProcessing(true)
    setMessage('')
    setError('')
    setResult(null)

    try {
      const response = await fetch(`${API}/procurement/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      })

      const body = await response.json()

      if (!response.ok) {
        throw new Error(body.detail ?? 'Procurement processing failed')
      }

      setResult(body as ProcessResponse)
      setMessage(body.message ?? 'Procurement processing completed.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not process requests')
    } finally {
      setProcessing(false)
    }
  }

  const totalRecords = summary.reduce((total, row) => total + row.records, 0)
  const hasImportedData = summary.some((row) => row.records > 0)

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">C</div>
          <div>
            <strong>cantill</strong>
            <span>PROCUREMENT OS</span>
          </div>
        </div>

        <div className="workspace-label">WORKSPACE</div>

        <div className="nav-item active">
          <Activity size={17} /> Overview
        </div>
        <div className="nav-item">
          <Package size={17} /> Purchase requests
        </div>
        <div className="nav-item">
          <Boxes size={17} /> Suppliers &amp; items
        </div>
        <div className="nav-item">
          <GitBranch size={17} /> Policy versions
        </div>
        <div className="nav-item">
          <FileText size={17} /> Audit trail
        </div>

        <div className="sidebar-bottom">
          <div className="avatar">GM</div>
          <div>
            <strong>Workspace Admin</strong>
            <span>Local development</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <span className="eyebrow">CORVO ENGINEERING / PROCUREMENT</span>
            <h1>Procurement workspace</h1>
          </div>

          <div className="top-actions">
            <span className={`status ${health === 'Connected' ? 'ok' : 'bad'}`}>
              <i /> API {health}
            </span>
            <button
              className="icon-button"
              onClick={() => void refresh()}
              aria-label="Refresh dashboard"
              title="Refresh dashboard"
            >
              <RefreshCw size={17} />
            </button>
          </div>
        </header>

        <section className="welcome">
          <div>
            <span className="eyebrow light">POLICY-DRIVEN PROCUREMENT</span>
            <h2>Procurement, with a clearer path forward.</h2>
            <p>
              Validate purchase requests, evaluate policy rules and find the
              right procurement route from one workspace.
            </p>
          </div>
          <div className="welcome-icon">
            <ShieldCheck size={54} />
          </div>
        </section>

        <section className="stats">
          <div className="stat-card">
            <span>Imported source records</span>
            <strong>{totalRecords.toLocaleString('en-IN')}</strong>
            <small>Across {summary.length} datasets</small>
          </div>

          <div className="stat-card">
            <span>Active policy version</span>
            <strong>v{policy}</strong>
            <small>Corvo Procurement Policy</small>
          </div>

          <div className="stat-card">
            <span>Database status</span>
            <strong className={health === 'Connected' ? 'stat-status' : 'stat-warning'}>
              {health === 'Connected' ? 'Online' : 'Pending'}
            </strong>
            <small>PostgreSQL connection</small>
          </div>
        </section>

        <section className="content-grid">
          <div className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">SOURCE DATA</span>
                <h3>Task-kit datasets</h3>
              </div>
              <span className="count-pill">{summary.length} loaded</span>
            </div>

            {summary.length === 0 ? (
              <div className="empty">
                <UploadCloud size={27} />
                <strong>No source data imported yet</strong>
                <span>Import the supplied CSV files to populate the workspace.</span>
              </div>
            ) : (
              <div className="dataset-list">
                {summary.map((row) => (
                  <div className="dataset-row" key={row.dataset}>
                    <div className="dataset-icon">
                      <FileText size={17} />
                    </div>
                    <div className="dataset-name">
                      <strong>{labels[row.dataset] ?? row.dataset}</strong>
                      <span>{row.dataset}</span>
                    </div>
                    <strong className="dataset-count">
                      {row.records.toLocaleString('en-IN')}
                    </strong>
                    <span className="loaded-dot" />
                  </div>
                ))}
              </div>
            )}

            <div className="panel-footer">
              <button
                className="primary-button"
                disabled={busy || health !== 'Connected'}
                onClick={() => void importData()}
              >
                {busy ? 'Importing…' : 'Import task-kit CSV data'}
                <ArrowUpRight size={16} />
              </button>
              <span>Safe to run again · replaces staged rows</span>
            </div>

            {message && !result && (
              <div className="notice success-notice">
                <CheckCircle2 size={16} />
                {message}
              </div>
            )}

            {error && (
              <div className="notice error-notice">
                <CircleAlert size={16} />
                {error}
              </div>
            )}
          </div>

          <div className="right-column">
            <div className="panel next-panel">
              <span className="eyebrow">PROCUREMENT ENGINE</span>
              <h3>Process purchase requests</h3>
              <p>
                Run the imported sample PR batch through validation, requirement
                clubbing, contract allocation, valuation and policy decisions.
              </p>

              <div className="engine-step">
                <span><ClipboardList size={16} /></span>
                <div>
                  <strong>Validate and consolidate</strong>
                  <small>Check PR lines and club matching requirements</small>
                </div>
              </div>

              <div className="engine-step">
                <span><GitBranch size={16} /></span>
                <div>
                  <strong>Evaluate policy rules</strong>
                  <small>Determine the correct procurement route</small>
                </div>
              </div>

              <div className="engine-step">
                <span><Truck size={16} /></span>
                <div>
                  <strong>Allocate and recommend</strong>
                  <small>Check contracts and eligible suppliers</small>
                </div>
              </div>

              <button
                className="process-button"
                disabled={
                  processing ||
                  health !== 'Connected' ||
                  !hasImportedData
                }
                onClick={() => void processBatch()}
              >
                {processing ? (
                  <>
                    <RefreshCw size={17} className="spin" />
                    Processing batch…
                  </>
                ) : (
                  <>
                    <Play size={16} fill="currentColor" />
                    Process sample PR batch
                  </>
                )}
              </button>

              {!hasImportedData && (
                <small className="helper-text">
                  Import the task-kit datasets before processing.
                </small>
              )}

              {result && (
                <div className="run-success">
                  <CheckCircle2 size={16} />
                  Last batch processed successfully
                </div>
              )}
            </div>

            <div className="tip">
              <ShieldCheck size={19} />
              <div>
                <strong>Policy as data</strong>
                <p>
                  Procurement rules are loaded from the active policy version
                  stored in PostgreSQL.
                </p>
              </div>
            </div>
          </div>
        </section>

        {error && result && (
          <div className="notice error-notice result-error">
            <CircleAlert size={16} />
            {error}
          </div>
        )}

        {result && (
          <section className="results-section">
            <div className="results-heading">
              <div>
                <span className="eyebrow">PROCESSING OUTPUT</span>
                <h2>Procurement results</h2>
                <p>
                  Policy v{result.policy?.version ?? policy} ·{' '}
                  {result.request_source === 'IMPORTED_SAMPLE_BATCH'
                    ? 'Imported sample batch'
                    : 'API-submitted batch'}
                </p>
              </div>
              <span className="result-status">
                <CheckCircle2 size={15} /> Completed
              </span>
            </div>

            <div className="result-stats">
              <div className="result-stat">
                <span>Input PR lines</span>
                <strong>{result.summary.total_input_lines}</strong>
              </div>
              <div className="result-stat">
                <span>Valid lines</span>
                <strong>{result.summary.valid_lines}</strong>
              </div>
              <div className="result-stat">
                <span>Invalid lines</span>
                <strong>{result.summary.invalid_lines}</strong>
              </div>
              <div className="result-stat">
                <span>Consolidated requirements</span>
                <strong>{result.summary.consolidated_requirements}</strong>
              </div>
            </div>

            <div className="result-columns">
              <div className="panel result-panel">
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">ROUTE DISTRIBUTION</span>
                    <h3>Procurement routes</h3>
                  </div>
                </div>

                {Object.entries(result.summary.route_summary ?? {}).length === 0 ? (
                  <p className="muted">No procurement routes were returned.</p>
                ) : (
                  <div className="distribution-list">
                    {Object.entries(result.summary.route_summary).map(([route, count]) => (
                      <div className="distribution-row" key={route}>
                        <span>{formatLabel(route)}</span>
                        <strong>{count}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="panel result-panel">
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">DECISION DISTRIBUTION</span>
                    <h3>Decision types</h3>
                  </div>
                </div>

                {Object.entries(result.summary.decision_summary ?? {}).length === 0 ? (
                  <p className="muted">No procurement decisions were returned.</p>
                ) : (
                  <div className="distribution-list">
                    {Object.entries(result.summary.decision_summary).map(([decision, count]) => (
                      <div className="distribution-row" key={decision}>
                        <span>{formatLabel(decision)}</span>
                        <strong>{count}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="panel detailed-results">
              <div className="panel-heading results-table-heading">
                <div>
                  <span className="eyebrow">REQUIREMENT REVIEW</span>
                  <h3>Processing details</h3>
                </div>

                <div className="tab-buttons">
                  <button
                    className={activeTab === 'requirements' ? 'tab active-tab' : 'tab'}
                    onClick={() => setActiveTab('requirements')}
                  >
                    Requirements ({result.requirement_results.length})
                  </button>
                  <button
                    className={activeTab === 'invalid' ? 'tab active-tab' : 'tab'}
                    onClick={() => setActiveTab('invalid')}
                  >
                    Invalid lines ({result.invalid_lines.length})
                  </button>
                </div>
              </div>

              {activeTab === 'requirements' ? (
                result.requirement_results.length === 0 ? (
                  <div className="empty compact-empty">
                    <Package size={25} />
                    <strong>No requirement results</strong>
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Requirement</th>
                          <th>Item</th>
                          <th>Plant</th>
                          <th>Quantity</th>
                          <th>Value</th>
                          <th>Route</th>
                          <th>Decision</th>
                          <th>Contract</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.requirement_results.map((item) => (
                          <tr key={item.requirement_id}>
                            <td>
                              <strong>{item.requirement_id}</strong>
                              <small>{item.line_count ?? 1} PR line(s)</small>
                            </td>
                            <td>{item.item_code || 'New item'}</td>
                            <td>{item.plant ?? '—'}</td>
                            <td>{item.total_quantity ?? '—'}</td>
                            <td>{formatCurrency(item.total_value)}</td>
                            <td>
                              <span className="route-pill">
                                {formatLabel(item.route)}
                              </span>
                            </td>
                            <td>{formatLabel(item.decision)}</td>
                            <td>{item.contract_id ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              ) : (
                result.invalid_lines.length === 0 ? (
                  <div className="empty compact-empty">
                    <CheckCircle2 size={25} />
                    <strong>No invalid PR lines</strong>
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>PR number</th>
                          <th>Line</th>
                          <th>Item</th>
                          <th>Plant</th>
                          <th>Validation errors</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.invalid_lines.map((line, index) => (
                          <tr key={`${line.pr_no}-${line.pr_line}-${index}`}>
                            <td>{line.pr_no ?? '—'}</td>
                            <td>{line.pr_line ?? '—'}</td>
                            <td>{line.item_code ?? '—'}</td>
                            <td>{line.plant ?? '—'}</td>
                            <td>
                              <span className="error-text">
                                {(line.validation_errors ?? []).join(', ') || 'Invalid line'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              )}
            </div>

            <div className="panel supplier-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">SUPPLIER INTELLIGENCE</span>
                  <h3>Recommended suppliers</h3>
                </div>
              </div>

              {result.requirement_results.some(
                (item) => (item.recommended_suppliers?.length ?? 0) > 0,
              ) ? (
                <div className="supplier-recommendations">
                  {result.requirement_results
                    .filter((item) => (item.recommended_suppliers?.length ?? 0) > 0)
                    .map((item) => (
                      <div className="recommendation-group" key={item.requirement_id}>
                        <div className="recommendation-title">
                          <strong>{item.requirement_id}</strong>
                          <span>{item.item_code ?? 'New item'} · {item.plant ?? '—'}</span>
                        </div>

                        <div className="supplier-list">
                          {(item.recommended_suppliers ?? []).map((supplier, index) => (
                            <div
                              className="supplier-row"
                              key={`${item.requirement_id}-${supplier.supplier_id ?? index}`}
                            >
                              <div className="supplier-rank">{index + 1}</div>
                              <div className="supplier-info">
                                <strong>{supplier.supplier_name ?? supplier.supplier_id ?? 'Supplier'}</strong>
                                <small>{supplier.supplier_id ?? 'ID unavailable'}</small>
                              </div>
                              <div className="supplier-score">
                                {supplier.ranking_score !== undefined
                                  ? `Score ${Number(supplier.ranking_score).toFixed(3)}`
                                  : 'Recommended'}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <p className="muted">
                  No supplier recommendations were returned for this batch.
                </p>
              )}
            </div>

            <div className="limitations-note">
              <CircleAlert size={17} />
              <div>
                <strong>Processing note</strong>
                <p>
                  Contract allocations are calculated in memory. They are not
                  permanently reserved, and decisions are not yet persisted as
                  audit records.
                </p>
              </div>
            </div>
          </section>
        )}

        <footer>
          CANTILL PROCUREMENT · LOCAL DEVELOPMENT
          <span>
            API documentation{' '}
            <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
              Open Swagger ↗
            </a>
          </span>
        </footer>
      </main>
    </div>
  )
}

export default App
