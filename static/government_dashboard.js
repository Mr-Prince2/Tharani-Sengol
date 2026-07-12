// Government Compliance & Enforcement Dashboard JS
document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize Leaflet Map
    const map = L.map('govMap').setView([10.816, 78.730], 8);
    
    // Add tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(map);

    // Bounding Boxes / Forbidden Polygons
    const forbiddenZones = {
        "forbidden_zone_1": {
            "name": "Cauvery River Protected Basin (Illegal Mining Zone A)",
            "coords": [
                [10.85, 78.50],
                [10.85, 78.55],
                [10.90, 78.55],
                [10.90, 78.50]
            ]
        },
        "forbidden_zone_2": {
            "name": "Pachaimalai Forest Reserve (Illegal Mining Zone B)",
            "coords": [
                [11.10, 78.65],
                [11.10, 78.75],
                [11.20, 78.75],
                [11.20, 78.65]
            ]
        }
    };

    // Draw Forbidden zones
    Object.values(forbiddenZones).forEach(zone => {
        L.polygon(zone.coords, {
            color: '#dc2626',
            fillColor: '#dc2626',
            fillOpacity: 0.25,
            weight: 2,
            dashArray: '5, 5'
        }).addTo(map).bindPopup(`<strong>CRITICAL GEOFENCE:</strong><br>${zone.name}`);
    });

    let routesData = {};
    let permitsList = [];
    let vehicleMarkers = {};
    let heatmapLayer = null;

    // 2. Fetch and draw Routes, Mine and Dump zones
    fetch("/api/routes")
        .then(res => res.json())
        .then(routes => {
            routesData = routes;
            Object.values(routes).forEach(route => {
                // Plot Route Line
                if (route.path && route.path.length > 0) {
                    L.polyline(route.path, {
                        color: route.color || '#4285f4',
                        weight: 2,
                        opacity: 0.4
                    }).addTo(map);
                }

                // Plot Mine Zone
                if (route.mine_zone && route.mine_zone.polygon) {
                    L.polygon(route.mine_zone.polygon, {
                        color: route.color || '#4285f4',
                        fillColor: route.color || '#4285f4',
                        fillOpacity: 0.15,
                        weight: 1.5
                    }).addTo(map).bindPopup(`<strong>Mine Zone:</strong> ${route.mine_zone.name}<br>Approved for Route: ${route.name}`);
                }

                // Plot Dump Zone
                if (route.dump_zone && route.dump_zone.polygon) {
                    L.polygon(route.dump_zone.polygon, {
                        color: '#16a34a',
                        fillColor: '#16a34a',
                        fillOpacity: 0.1,
                        weight: 1
                    }).addTo(map).bindPopup(`<strong>Dump Zone:</strong> ${route.dump_zone.name}`);
                }
            });
        });

    // 3. Populate Lorry Markers
    function updateLorryMarkers() {
        fetch("/api/vehicles")
            .then(res => res.json())
            .then(vehicles => {
                // Get snapshots to determine risk colors
                fetch("/api/high-risk-vehicles")
                    .then(res => res.json())
                    .then(highRisk => {
                        const riskMap = {};
                        highRisk.forEach(v => {
                            riskMap[v.vehicle_id] = v.risk;
                        });

                        Object.keys(vehicles).forEach(vehicleId => {
                            const v = vehicles[vehicleId];
                            const risk = riskMap[vehicleId] || 0;
                            
                            // Color code marker
                            let color = '#16a34a'; // green
                            if (risk >= 80) color = '#dc2626'; // red
                            else if (risk >= 50) color = '#d97706'; // yellow

                            if (v.lat !== undefined && v.lat !== null && v.lon !== undefined && v.lon !== null) {
                                const customMarker = L.circleMarker([v.lat, v.lon], {
                                    radius: 6,
                                    fillColor: color,
                                    color: '#ffffff',
                                    weight: 1,
                                    fillOpacity: 0.95
                                });

                                if (vehicleMarkers[vehicleId]) {
                                    map.removeLayer(vehicleMarkers[vehicleId]);
                                }

                                customMarker.addTo(map).bindPopup(`
                                    <strong>Lorry:</strong> ${vehicleId}<br>
                                    <strong>Route:</strong> ${v.route_name || 'N/A'}<br>
                                    <strong>Risk Score:</strong> ${Math.round(risk)}<br>
                                    <strong>Location:</strong> ${v.lat.toFixed(4)}, ${v.lon.toFixed(4)}
                                `);
                                vehicleMarkers[vehicleId] = customMarker;
                            }
                        });
                    });
            });
    }

    // 4. Update Stats & Tables
    function loadDashboardData() {
        // Fetch permits list
        fetch("/api/permits")
            .then(res => res.json())
            .then(permits => {
                permitsList = permits;
                document.getElementById("govActivePermits").textContent = permits.filter(p => p.status === 'active').length;
                
                // Populate searchable datalist
                const datalist = document.getElementById("checkpointTrucksList");
                if (datalist && datalist.children.length <= 1) {
                    datalist.innerHTML = '';
                    permits.forEach(p => {
                        const option = document.createElement("option");
                        option.value = p.vehicle_number;
                        option.textContent = `Permit: ${p.permit_id} (Route: ${p.approved_route})`;
                        datalist.appendChild(option);
                    });
                }
                
                // Tonnage Tracker
                let totalTonnage = 0.0;
                const trackerBody = document.getElementById("govTonnageTrackerBody");
                trackerBody.innerHTML = '';
                permits.forEach(p => {
                    totalTonnage += p.used_quantity;
                    const percent = Math.min(100, Math.round((p.used_quantity / p.max_quantity) * 100));
                    const isExceeded = p.used_quantity > p.max_quantity;
                    const rowClass = isExceeded ? 'style="background: rgba(220, 38, 38, 0.08);"' : '';
                    
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${p.permit_id}</strong></td>
                        <td>${p.vehicle_number}</td>
                        <td>${p.approved_route}</td>
                        <td>${p.max_quantity.toFixed(1)} T</td>
                        <td ${isExceeded ? 'class="muted" style="color:var(--danger); font-weight:bold;"' : ''}>${p.used_quantity.toFixed(1)} T</td>
                        <td>
                            <div style="background:rgba(255,255,255,0.06); width:100px; height:8px; border-radius:4px; overflow:hidden;">
                                <div style="width:${percent}%; height:100%; background:${isExceeded ? 'var(--danger)' : 'var(--success)'};"></div>
                            </div>
                        </td>
                    `;
                    if (rowClass) tr.style.background = "rgba(220, 38, 38, 0.06)";
                    trackerBody.appendChild(tr);
                });
                document.getElementById("govTotalQuantity").textContent = `${totalTonnage.toFixed(1)} T`;
            });

        // Fetch permit violations
        fetch("/api/permit-violations")
            .then(res => res.json())
            .then(violations => {
                document.getElementById("govPermitViolations").textContent = violations.length;
                if (violations.length > 0) {
                    document.getElementById("govPermitViolations").className = "muted";
                    document.getElementById("govPermitViolations").style.color = "var(--warning)";
                } else {
                    document.getElementById("govPermitViolations").className = "muted";
                    document.getElementById("govPermitViolations").style.color = "var(--text)";
                }

                const violationsBody = document.getElementById("govPermitViolationsBody");
                violationsBody.innerHTML = '';
                if (violations.length === 0) {
                    violationsBody.innerHTML = '<tr><td colspan="6" class="muted text-center">No permit compliance infractions detected.</td></tr>';
                } else {
                    violations.forEach(v => {
                        const tr = document.createElement("tr");
                        tr.innerHTML = `
                            <td><strong style="color:var(--warning);">${v.permit_id}</strong></td>
                            <td>${v.vehicle_number}</td>
                            <td>${v.used_quantity.toFixed(1)}/${v.max_quantity.toFixed(1)} T</td>
                            <td>${v.completed_trips}/${v.max_trips}</td>
                            <td><span class="badge ${v.status === 'active' ? 'safe' : 'danger'}">${v.status.toUpperCase()}</span></td>
                            <td style="color:var(--warning); font-size:11px;">${v.violations.join(", ")}</td>
                        `;
                        violationsBody.appendChild(tr);
                    });
                }
            });

        // Fetch illegal trips violations
        fetch("/api/illegal-trips")
            .then(res => res.json())
            .then(trips => {
                const tripsBody = document.getElementById("govIllegalTripsBody");
                tripsBody.innerHTML = '';
                if (trips.length === 0) {
                    tripsBody.innerHTML = '<tr><td colspan="5" class="muted text-center">No recent geo-spatial or overloading violations logged.</td></tr>';
                } else {
                    trips.forEach(t => {
                        const isCritical = t.severity === 'critical';
                        const time = new Date(t.event_time).toLocaleTimeString();
                        const tr = document.createElement("tr");
                        tr.innerHTML = `
                            <td class="muted">${time}</td>
                            <td><strong>${t.vehicle_id}</strong></td>
                            <td style="color:${isCritical ? 'var(--danger)' : 'var(--warning)'}; font-weight:${isCritical ? 'bold' : 'normal'}">${t.reason}</td>
                            <td>${t.route_name || 'N/A'}</td>
                            <td><span class="badge ${isCritical ? 'danger' : 'suspicious'}">${t.severity.toUpperCase()}</span></td>
                        `;
                        tripsBody.appendChild(tr);
                    });
                }
            });

        // Fetch suspicious/blacklisted fleet
        fetch("/api/high-risk-vehicles")
            .then(res => res.json())
            .then(fleet => {
                document.getElementById("govBlacklistedCount").textContent = fleet.filter(f => f.risk >= 80).length;
                const blacklistBody = document.getElementById("govBlacklistedFleetBody");
                blacklistBody.innerHTML = '';
                
                if (fleet.length === 0) {
                    blacklistBody.innerHTML = '<tr><td colspan="5" class="muted text-center">No blacklisted vehicles currently flagged.</td></tr>';
                } else {
                    fleet.forEach(f => {
                        // Look up permit ID
                        const p = permitsList.find(p => p.vehicle_number === f.vehicle_id);
                        const permitId = p ? p.permit_id : '';
                        const permitStatus = p ? p.status : 'active';
                        
                        const tr = document.createElement("tr");
                        tr.innerHTML = `
                            <td><strong>${f.vehicle_id}</strong></td>
                            <td><span class="badge ${f.risk >= 80 ? 'danger' : 'suspicious'}">${Math.round(f.risk)} risk</span></td>
                            <td><span class="badge ${permitStatus === 'active' ? 'safe' : 'danger'}">${permitStatus.toUpperCase()}</span></td>
                            <td class="muted" style="font-size:11px;">${f.last_event || 'N/A'}</td>
                            <td>
                                ${permitStatus === 'active' 
                                    ? `<button type="button" class="btn" style="background:var(--danger); border-color:var(--danger); padding:4px 8px; font-size:10px;" onclick="revokePermit('${permitId}')">Revoke Permit</button>`
                                    : `<span class="muted" style="font-size:10px;">Enforced</span>`
                                }
                            </td>
                        `;
                        blacklistBody.appendChild(tr);
                    });
                }
            });
            
        // Load Heatmap points
        fetch("/api/heatmap-data")
            .then(res => res.json())
            .then(points => {
                if (heatmapLayer) {
                    map.removeLayer(heatmapLayer);
                }
                const formatted = points.map(p => [p.lat, p.lon, p.weight]);
                heatmapLayer = L.heatLayer(formatted, {
                    radius: 20,
                    blur: 15,
                    maxZoom: 10,
                    gradient: {0.4: 'blue', 0.6: 'lime', 0.8: 'orange', 1.0: 'red'}
                }).addTo(map);
            });
    }

    // 5. Revoke permit handler (attaches to global scope so button onclick works)
    window.revokePermit = function(permitId) {
        if (!permitId) return;
        if (!confirm(`Are you sure you want to revoke permit ${permitId}? This lorry will immediately raise critical alerts for all subsequent movements.`)) {
            return;
        }

        fetch("/api/permit/revoke", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ permit_id: permitId })
        })
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                loadDashboardData();
                updateLorryMarkers();
            }
        });
    };

    // 6. QR/RFID Simulation click listeners
    const scanResultPanel = document.getElementById("checkpointScanResult");

    document.getElementById("checkpointQrBtn").addEventListener("click", () => {
        const searchValue = document.getElementById("checkpointTruckSearch").value.trim();
        if (!searchValue) {
            alert("Please type or search a lorry ID or permit ID first!");
            return;
        }

        const permit = permitsList.find(p => p.vehicle_number.toLowerCase() === searchValue.toLowerCase() || p.permit_id.toLowerCase() === searchValue.toLowerCase());
        if (!permit) {
            scanResultPanel.innerHTML = `<p class="muted" style="color:var(--danger);">No permit registered for "${searchValue}".</p>`;
            return;
        }
        const vehicleId = permit.vehicle_number;

        scanResultPanel.innerHTML = '<p class="muted">Generating dynamic QR code...</p>';
        fetch(`/api/permit/${permit.permit_id}/qr`)
            .then(res => res.json())
            .then(data => {
                if (data.qr_image_base64) {
                    scanResultPanel.innerHTML = `
                        <div style="display:grid; grid-template-columns: 140px 1fr; gap:12px; text-align:left; align-items:center;">
                            <div>
                                <img src="${data.qr_image_base64}" alt="Permit QR" style="width:130px; height:130px; border:4px solid white; border-radius:8px;" />
                            </div>
                            <div class="vehicle-meta">
                                <strong>Permit ID:</strong> <span style="color:var(--accent); font-weight:bold;">${data.permit_id}</span><br>
                                <strong>Lorry Registration:</strong> ${data.payload.vehicle_number}<br>
                                <strong>Approved Route ID:</strong> ${data.payload.approved_route}<br>
                                <strong>Max Excavation Tonnage:</strong> ${data.payload.max_quantity} Tons<br>
                                <strong>Validity Period:</strong> ${data.payload.valid_from} to ${data.payload.valid_to}<br>
                                <strong>Current Permit Status:</strong> <span class="badge ${data.payload.status === 'active' ? 'safe' : 'danger'}">${data.payload.status.toUpperCase()}</span>
                            </div>
                        </div>
                    `;
                } else {
                    scanResultPanel.innerHTML = `<p class="muted" style="color:var(--danger);">Failed to load QR code: ${data.message || 'Unknown error'}</p>`;
                }
            });
    });

    document.getElementById("checkpointVerifyBtn").addEventListener("click", () => {
        const searchValue = document.getElementById("checkpointTruckSearch").value.trim();
        if (!searchValue) {
            alert("Please type or search a lorry ID or permit ID first!");
            return;
        }

        const permit = permitsList.find(p => p.vehicle_number.toLowerCase() === searchValue.toLowerCase() || p.permit_id.toLowerCase() === searchValue.toLowerCase());
        if (!permit) {
            scanResultPanel.innerHTML = `<p class="muted" style="color:var(--danger);">Verification failed: Lorry/Permit "${searchValue}" is completely unregistered!</p>`;
            return;
        }
        const vehicleId = permit.vehicle_number;

        // Get live vehicle details
        fetch("/api/vehicles")
            .then(res => res.json())
            .then(vehicles => {
                const liveRouteId = vehicles[vehicleId] ? vehicles[vehicleId].route_id : null;
                
                scanResultPanel.innerHTML = '<p class="muted">Authenticating credentials with Government servers...</p>';
                
                fetch("/api/permit/verify", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        permit_id: permit.permit_id,
                        vehicle_number: vehicleId,
                        route_id: liveRouteId
                    })
                })
                .then(res => res.json())
                .then(resData => {
                    const c = resData.checks;
                    const p = resData.permit;
                    const isValid = resData.valid;

                    scanResultPanel.innerHTML = `
                        <div style="text-align:left;">
                            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:6px; margin-bottom:8px;">
                                <strong>Verification Check Result:</strong>
                                <span class="badge ${isValid ? 'safe' : 'danger'}" style="font-size:12px;">${isValid ? 'PASSED / COMPLIANT' : 'FAILED / NON-COMPLIANT'}</span>
                            </div>
                            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:11px;" class="vehicle-meta">
                                <div>
                                    <strong>Permit Registered:</strong> <span class="status-${c.registered ? 'no' : 'yes'}">${c.registered ? 'YES' : 'NO'}</span><br>
                                    <strong>Status Active:</strong> <span class="status-${c.active ? 'no' : 'yes'}">${c.active ? 'YES' : 'NO'}</span><br>
                                    <strong>Date Valid:</strong> <span class="status-${c.date_valid ? 'no' : 'yes'}">${c.date_valid ? 'YES' : 'NO'}</span>
                                </div>
                                <div>
                                    <strong>Approved Route Line:</strong> <span class="status-${c.route_valid ? 'no' : 'yes'}">${c.route_valid ? 'YES' : 'NO'}</span><br>
                                    <strong>Trips Within Cap:</strong> <span class="status-${c.trips_valid ? 'no' : 'yes'}">${c.trips_valid ? 'YES' : 'NO'}</span><br>
                                    <strong>Tonnage Within Cap:</strong> <span class="status-${c.quantity_valid ? 'no' : 'yes'}">${c.quantity_valid ? 'YES' : 'NO'}</span>
                                </div>
                            </div>
                            ${resData.errors.length > 0 
                                ? `<div style="margin-top:10px; padding:6px; background:rgba(220,38,38,0.15); border:1px solid rgba(220,38,38,0.3); border-radius:6px; font-size:11px; color:#fecaca;">
                                     <strong>Infractions:</strong>
                                     <ul style="margin:4px 0 0; padding-left:14px;">
                                         ${resData.errors.map(err => `<li>${err}</li>`).join("")}
                                     </ul>
                                   </div>`
                                : '<div style="margin-top:10px; padding:6px; background:rgba(22,163,74,0.12); border:1px solid rgba(22,163,74,0.3); border-radius:6px; font-size:11px; color:#bbf7d0;">Lorry is fully authorized to transport excavated earth.</div>'
                            }
                        </div>
                    `;
                });
            });
    });

    document.getElementById("checkpointRfidBtn").addEventListener("click", () => {
        const searchValue = document.getElementById("checkpointTruckSearch").value.trim();
        if (!searchValue) {
            alert("Please type or search a lorry ID or permit ID first!");
            return;
        }

        const permit = permitsList.find(p => p.vehicle_number.toLowerCase() === searchValue.toLowerCase() || p.permit_id.toLowerCase() === searchValue.toLowerCase());
        if (!permit) {
            scanResultPanel.innerHTML = `<p class="muted" style="color:var(--danger);">RFID Cross Failed: Unregistered RFID tag detected for "${searchValue}"!</p>`;
            return;
        }
        const vehicleId = permit.vehicle_number;

        fetch("/api/vehicles")
            .then(res => res.json())
            .then(vehicles => {
                const liveRouteId = vehicles[vehicleId] ? vehicles[vehicleId].route_id : null;
                scanResultPanel.innerHTML = '<p class="muted">Reading RFID tag coordinates...</p>';
                
                fetch("/api/permit/verify", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        permit_id: permit.permit_id,
                        vehicle_number: vehicleId,
                        route_id: liveRouteId
                    })
                })
                .then(res => res.json())
                .then(resData => {
                    const isValid = resData.valid;
                    
                    scanResultPanel.innerHTML = `
                        <div style="text-align:left; border: 1px dashed var(--accent); padding:10px; border-radius:8px; background:rgba(47, 111, 237, 0.04);">
                            <div style="font-size:13px; font-weight:bold; color:var(--accent); margin-bottom:6px;">
                                RFID Checkpoint Crossing Event
                            </div>
                            <p style="font-size:11px; margin:0 0 8px;" class="muted">
                                <strong>Checkpoint Sensor:</strong> Trichy Tollgate #4<br>
                                <strong>Detected Vehicle:</strong> ${vehicleId}<br>
                                <strong>RFID UID:</strong> E28011320000${(vehicleId.split("_")[1] || vehicleId)}
                            </p>
                            <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:8px; border-radius:6px;">
                                <span style="font-size:12px; font-weight:bold;">Enforcement Decision:</span>
                                <span class="badge ${isValid ? 'safe' : 'danger'}">${isValid ? 'GO / APPROVED' : 'HOLD / DETEND'}</span>
                            </div>
                            ${!isValid 
                                ? `<p style="color:var(--danger); font-size:10px; margin-top:6px; font-weight:bold;">Alert logged to central enforcement registry.</p>`
                                : `<p style="color:var(--success); font-size:10px; margin-top:6px;">Lorry logs recorded successfully.</p>`
                            }
                        </div>
                    `;
                });
            });
    });

    // 7. Initial updates
    updateLorryMarkers();
    loadDashboardData();

    // Loop timers
    setInterval(updateLorryMarkers, 3500);
    setInterval(loadDashboardData, 6000);
});
