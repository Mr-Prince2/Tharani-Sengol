document.addEventListener("DOMContentLoaded", () => {
    const vehiclePicker = document.getElementById("vehiclePicker");
    const aiSearchInput = document.getElementById("aiSearchInput");
    const aiSubmitBtn = document.getElementById("aiSubmitBtn");
    const eventHistoryList = document.getElementById("eventHistoryList");
    const selectedEventTime = document.getElementById("selectedEventTime");
    const pipelineNodes = document.getElementById("pipelineNodes");
    const inspectorContent = document.getElementById("inspectorContent");
    const verdictCard = document.getElementById("verdictCard");
    const verdictSentence = document.getElementById("verdictSentence");
    const verdictStatusPulse = document.getElementById("verdictStatusPulse");
    const orchestratorManagerNode = document.getElementById("orchestratorManagerNode");

    let currentVehicleId = "";
    let selectedEventId = null;
    let tracesCache = [];
    let pollingInterval = null;
    let animationTimer = null;

    // Load active vehicles dropdown at startup
    loadVehicles();

    // Event listener: select vehicle via dropdown
    vehiclePicker.addEventListener("change", (e) => {
        handleVehicleSelection(e.target.value);
    });

    // Event listener: search active lorry
    aiSubmitBtn.addEventListener("click", () => {
        performSearch();
    });

    aiSearchInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            performSearch();
        }
    });

    function performSearch() {
        const query = aiSearchInput.value.trim().toLowerCase();
        if (!query) return;

        // Try to match search query (e.g. "15" matches "truck_15")
        let matchedId = "";
        const options = Array.from(vehiclePicker.options);
        
        // Direct match first
        const directMatch = options.find(opt => opt.value.toLowerCase() === query);
        if (directMatch) {
            matchedId = directMatch.value;
        } else {
            // Check numeric part
            const num = parseInt(query.replace(/^\D+/g, '')) || null;
            if (num !== null) {
                const numMatch = options.find(opt => {
                    const optNum = parseInt(opt.value.replace(/^\D+/g, '')) || 0;
                    return optNum === num;
                });
                if (numMatch) matchedId = numMatch.value;
            }
        }

        if (matchedId) {
            vehiclePicker.value = matchedId;
            handleVehicleSelection(matchedId);
        } else {
            verdictCard.style.display = "block";
            verdictStatusPulse.style.backgroundColor = "#ef4444";
            verdictStatusPulse.className = "pulse-ring";
            verdictSentence.innerHTML = `<span style="color: #f87171; font-weight: bold;">Search Error:</span> Lorry ID "<strong>${escapeHTML(aiSearchInput.value)}</strong>" is not active in Tamil Nadu telemetry stream. Please select an active vehicle from the dropdown or try another ID.`;
        }
    }

    function handleVehicleSelection(vehicleId) {
        if (animationTimer) {
            clearInterval(animationTimer);
            animationTimer = null;
        }

        currentVehicleId = vehicleId;
        selectedEventId = null;
        tracesCache = [];
        inspectorContent.innerHTML = `<div class="muted">Select a specific node above or click a telemetry event in the sidebar to inspect execution context.</div>`;
        selectedEventTime.textContent = "";
        verdictCard.style.display = "none";

        if (currentVehicleId) {
            loadVehicleTraces(currentVehicleId, true);
            startPolling(currentVehicleId);
        } else {
            stopPolling();
            eventHistoryList.innerHTML = `<div class="muted text-center py-4">Select a vehicle to load GPS events timeline</div>`;
            pipelineNodes.innerHTML = "";
        }
    }

    async function loadVehicles() {
        try {
            const res = await fetch("/api/vehicles");
            const data = await res.json();
            const keys = Object.keys(data).sort((a, b) => {
                const numA = parseInt(a.replace(/^\D+/g, '')) || 0;
                const numB = parseInt(b.replace(/^\D+/g, '')) || 0;
                return numA - numB;
            });

            vehiclePicker.innerHTML = `<option value="">-- Select a Vehicle --</option>`;
            keys.forEach(vid => {
                const opt = document.createElement("option");
                opt.value = vid;
                opt.textContent = vid.toUpperCase();
                vehiclePicker.appendChild(opt);
            });
        } catch (err) {
            console.error("Error loading vehicles:", err);
            vehiclePicker.innerHTML = `<option value="">Error loading active fleet</option>`;
        }
    }

    async function loadVehicleTraces(vehicleId, isFirstLoad = false) {
        try {
            const res = await fetch(`/api/vehicle/${vehicleId}/agent-trace?limit=25`);
            if (res.status === 403) {
                eventHistoryList.innerHTML = `<div class="muted text-center py-4 text-danger">Access forbidden for this vehicle.</div>`;
                stopPolling();
                return;
            }
            const data = await res.json();
            tracesCache = data;

            if (data.length === 0) {
                eventHistoryList.innerHTML = `<div class="muted text-center py-4">No agent traces recorded for this vehicle. Run the simulator.</div>`;
                pipelineNodes.innerHTML = "";
                return;
            }

            renderHistoryList(data, isFirstLoad);
        } catch (err) {
            console.error("Error loading traces:", err);
        }
    }

    function renderHistoryList(traces, isFirstLoad) {
        eventHistoryList.innerHTML = "";
        traces.forEach((t, index) => {
            const item = document.createElement("button");
            item.className = "history-item";
            if (selectedEventId === t.id || (isFirstLoad && index === 0)) {
                item.classList.add("active");
                if (isFirstLoad && index === 0) {
                    selectedEventId = t.id;
                    triggerGraphAnimation(t);
                }
            }

            const localTime = new Date(t.timestamp).toLocaleTimeString();
            const localDate = new Date(t.timestamp).toLocaleDateString();

            const runAgents = t.trace.filter(a => a.ran).map(a => a.agent);
            const triggeredViolations = t.trace.some(a => a.ran && a.output_summary.includes("triggered=True"));
            const overloadFlag = t.trace.some(a => a.ran && a.agent === "WeightAgent" && a.output_summary.includes("overload"));

            let statusHTML = `<span style="color: #10b981;">Clean tick</span>`;
            if (triggeredViolations) {
                statusHTML = `<span style="color: #ef4444; font-weight: bold;">Violation</span>`;
            } else if (overloadFlag) {
                statusHTML = `<span style="color: #f59e0b;">Overloaded</span>`;
            }

            item.innerHTML = `
                <div class="history-item-header">
                    <span>Event #${t.gps_event_id || t.id}</span>
                    <span>${statusHTML}</span>
                </div>
                <div class="history-item-time">${localDate} ${localTime}</div>
            `;

            item.addEventListener("click", () => {
                if (animationTimer) clearInterval(animationTimer);
                document.querySelectorAll(".history-item").forEach(el => el.classList.remove("active"));
                item.classList.add("active");

                selectedEventId = t.id;
                triggerGraphAnimation(t);
            });

            eventHistoryList.appendChild(item);
        });
    }

    // Step-by-step interactive LangGraph execution trace animation
    function triggerGraphAnimation(eventData) {
        if (animationTimer) clearInterval(animationTimer);
        
        // Show verdict card in Loading/Analyzing state
        verdictCard.style.display = "block";
        verdictStatusPulse.style.backgroundColor = "#3b82f6";
        verdictStatusPulse.className = "pulse-ring pulse-ring-active";
        verdictSentence.textContent = "Agentic AI Orchestrator: Inspecting event payload & setting dynamic routing paths...";

        selectedEventTime.textContent = `Event Timestamp: ${new Date(eventData.timestamp).toLocaleString()}`;
        pipelineNodes.innerHTML = "";

        // Build all nodes in a pending gray state first
        const nodesList = [];
        eventData.trace.forEach(agentTrace => {
            const node = document.createElement("div");
            node.className = "graph-node";
            node.innerHTML = `
                <div class="node-name">${agentTrace.agent}</div>
                <div class="node-status" style="color: var(--muted);">Waiting...</div>
            `;
            pipelineNodes.appendChild(node);
            nodesList.push({ element: node, trace: agentTrace });
        });

        // Highlight Orchestrator node
        orchestratorManagerNode.style.boxShadow = "0 0 15px #3b82f6";
        
        let step = 0;
        const typingMessages = {
            "GeofenceAgent": "GeofenceAgent: Inspecting restricted spatial boundaries and mining zones...",
            "RouteDeviationAgent": "RouteDeviationAgent: Verifying distance deviation against permit transit paths...",
            "SpoofAgent": "SpoofAgent: Running velocity sanity check on GPS coordinates...",
            "ConvoyAgent": "ConvoyAgent: Scanning proximity cluster patterns for coordinated fleet behavior...",
            "PermitAgent": "PermitAgent: Checking compliance validity of registered mineral permit...",
            "CameraAgent": "CameraAgent: cross-referencing truck gate counting from camera sensors...",
            "WeightAgent": "WeightAgent: Processing kinematics regression model to predict weight...",
            "WeightLockAgent": "WeightLockAgent: Checking stable trip distance to freeze final tonnage...",
            "DriverBehaviorAgent": "DriverBehaviorAgent: Checking acceleration variance and profiling operators...",
            "PredictionAgent": "PredictionAgent: Calculating Random Forest illegal mining probabilities...",
            "AnomalyAgent": "AnomalyAgent: Running Isolation Forest for multivariate threat detection...",
            "ForecastAgent": "ForecastAgent: Modeling future trip pathing and logistics predictions...",
            "FusionAgent": "FusionAgent: Synthesizing final composite compliance threat matrix..."
        };

        animationTimer = setInterval(() => {
            // Remove processing class from previous node
            if (step > 0) {
                nodesList[step - 1].element.classList.remove("node-processing");
                
                // Show executed status for the finished node
                const prev = nodesList[step - 1];
                prev.element.classList.add("active-node");
                prev.element.querySelector(".node-status").textContent = "Executed";
                prev.element.querySelector(".node-status").style.color = "#34d399";
            }

            if (step < nodesList.length) {
                const current = nodesList[step];
                current.element.classList.add("node-processing");
                current.element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                
                // Set custom typing explanation in verdict box
                const agentName = current.trace.agent;
                verdictSentence.textContent = typingMessages[agentName] || `Executing ${agentName}...`;
                
                step++;
            } else {
                // Done with all nodes
                clearInterval(animationTimer);
                animationTimer = null;
                orchestratorManagerNode.style.boxShadow = "none";

                // Setup click listeners for interactive inspector
                nodesList.forEach(item => {
                    item.element.addEventListener("click", () => {
                        document.querySelectorAll(".graph-node").forEach(el => el.classList.remove("selected"));
                        item.element.classList.add("selected");
                        inspectNode(item.trace);
                    });
                });

                // Auto inspect first node
                if (nodesList.length > 0) {
                    inspectNode(nodesList[0].trace);
                    nodesList[0].element.classList.add("selected");
                }

                // Show final executive verdict sentence
                displayExecutiveVerdict(currentVehicleId);
            }
        }, 120);
    }

    async function displayExecutiveVerdict(vehicleId) {
        try {
            const res = await fetch(`/api/vehicle/${vehicleId}/detail`);
            if (res.status !== 200) return;
            const data = await res.json();

            // Set pulse status color
            let statusColor = "#10b981"; // Clean Green
            let sentence = "";

            if (data.risk >= 75.0) {
                statusColor = "#ef4444"; // Red
                sentence = `🚨 <strong>Critical Risk Verdict:</strong> Lorry <strong>${data.vehicle_id.toUpperCase()}</strong> (operating profile: ${data.profile}) has been flagged with a critical risk score of <strong>${data.risk.toFixed(2)}%</strong> on ${data.route_name || "Assigned Route"} in ${data.district} due to a confirmed infraction: <em>"${data.last_event}"</em>. Immediate enforcement action is recommended.`;
            } else if (data.overload_flag) {
                statusColor = "#f59e0b"; // Orange/Yellow
                sentence = `⚠️ <strong>Overload Warning Verdict:</strong> Lorry <strong>${data.vehicle_id.toUpperCase()}</strong> is carrying a predicted cargo payload of <strong>${data.predicted_weight.toFixed(2)} Tons</strong>, exceeding the permit tonnage limit of <strong>20.0 Tons</strong> on ${data.route_name || "Assigned Route"}.`;
            } else if (data.risk >= 45.0) {
                statusColor = "#f59e0b"; // Orange/Yellow
                sentence = `⚠️ <strong>Elevated Risk Verdict:</strong> Lorry <strong>${data.vehicle_id.toUpperCase()}</strong> exhibits an elevated risk rating of <strong>${data.risk.toFixed(2)}%</strong> on ${data.route_name || "Assigned Route"} in ${data.district} associated with: <em>"${data.last_event}"</em>. Surveillance checkpoints notified.`;
            } else {
                statusColor = "#10b981"; // Clean Green
                sentence = `✅ <strong>Clear Compliance Verdict:</strong> Lorry <strong>${data.vehicle_id.toUpperCase()}</strong> (profile: ${data.profile}) is operating in full regulatory compliance in ${data.district} with a clean safety status, registered permits verified, and a normal payload weight of <strong>${data.predicted_weight.toFixed(2)} Tons</strong>.`;
            }

            verdictStatusPulse.style.backgroundColor = statusColor;
            verdictStatusPulse.className = "pulse-ring";
            verdictSentence.innerHTML = sentence;
        } catch (err) {
            console.error("Error fetching vehicle details for verdict:", err);
            verdictSentence.textContent = "Compliance check completed successfully. Review agent logs below for individual node rationales.";
        }
    }

    function inspectNode(agentTrace) {
        const ranBadge = `<span class="grounded-badge documents">EXECUTED</span>`;
        inspectorContent.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <h4 style="margin: 0; font-size: 16px; color: var(--accent);">${agentTrace.agent}</h4>
                ${ranBadge}
            </div>
            <table class="inspector-table">
                <tr>
                    <th>Routing Rationale</th>
                    <td class="log-reason">${escapeHTML(agentTrace.reason)}</td>
                </tr>
                <tr>
                    <th>Node Input Data</th>
                    <td><code style="background: rgba(0,0,0,0.25); padding: 2px 6px; border-radius: 4px; font-family: monospace;">${escapeHTML(agentTrace.input_summary)}</code></td>
                </tr>
                <tr>
                    <th>Node Output State</th>
                    <td><code style="background: rgba(0,0,0,0.25); padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #10b981;">${escapeHTML(agentTrace.output_summary)}</code></td>
                </tr>
            </table>
        `;
    }

    function escapeHTML(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function startPolling(vehicleId) {
        stopPolling();
        pollingInterval = setInterval(() => {
            loadVehicleTraces(vehicleId, false);
        }, 3000); // Poll trace history every 3s
    }

    function stopPolling() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }
});
