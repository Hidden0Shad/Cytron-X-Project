const API_BASE = "/api/v1";
let currentScenario = "scenario-1";
let loginStep = 1;

// UI HELPERS
function showAlert(msg, isError = false) {
    const box = document.getElementById("alert-box");
    box.textContent = msg;
    box.className = `fixed top-4 right-4 px-6 py-3 rounded shadow-lg text-white font-bold z-50 ${
        isError ? "bg-red-600" : "bg-green-500"
    }`;
    box.classList.remove("hidden");

    setTimeout(() => box.classList.add("hidden"), 4000);
}

function switchTab(scenario) {
    currentScenario = scenario;
    loginStep = 1;

    ["s1", "s2", "s3"].forEach(s => {
        const tab = document.getElementById(`tab-${s}`);

        tab.classList.remove("tab-active", "text-gray-500");

        if (`scenario-${s[1]}` === scenario) {
            tab.classList.add("tab-active");
        } else {
            tab.classList.add("text-gray-500");
        }
    });

    document.getElementById("otp-1").classList.add("hidden");
    document.getElementById("otp-1").value = "";

    document.getElementById("otp-2").classList.add("hidden");
    document.getElementById("otp-2").value = "";

    document.getElementById("password").classList.remove("hidden");
    document.getElementById("username").disabled = false;
    document.getElementById("login-btn").textContent = "Login";
}

// LOGIN
async function handleLogin() {
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const otp1 = document.getElementById("otp-1").value;
    const otp2 = document.getElementById("otp-2").value;

    try {
        if (currentScenario === "scenario-1") {
            const res = await fetch(`${API_BASE}/auth/login-scenario-1`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });

            processLoginResponse(await res.json(), res.status);
        }

        else if (currentScenario === "scenario-2") {
            if (loginStep === 1) {
                const res = await fetch(`${API_BASE}/auth/login-scenario-2/step1`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });

                const data = await res.json();

                if (res.status === 200) {
                    showAlert("Check Console/Mailtrap for OTP");

                    loginStep = 2;

                    document.getElementById("password").classList.add("hidden");
                    document.getElementById("username").disabled = true;
                    document.getElementById("otp-1").classList.remove("hidden");
                    document.getElementById("login-btn").textContent = "Verify OTP";
                } else {
                    showAlert(data.error, true);
                }
            }

            else if (loginStep === 2) {
                const res = await fetch(`${API_BASE}/auth/login-scenario-2/step2`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username,
                        otp: otp1
                    })
                });

                processLoginResponse(await res.json(), res.status);
            }
        }

        else if (currentScenario === "scenario-3") {
            if (loginStep === 1) {
                const res = await fetch(`${API_BASE}/auth/login-scenario-3/step1`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });

                const data = await res.json();

                if (res.status === 200) {
                    showAlert("Check Console/Mailtrap for Primary OTP");

                    loginStep = 2;

                    document.getElementById("password").classList.add("hidden");
                    document.getElementById("username").disabled = true;
                    document.getElementById("otp-1").classList.remove("hidden");
                    document.getElementById("login-btn").textContent = "Verify Primary OTP";
                } else {
                    showAlert(data.error, true);
                }
            }

            else if (loginStep === 2) {
                const res = await fetch(`${API_BASE}/auth/login-scenario-3/step2`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username,
                        otp: otp1
                    })
                });

                const data = await res.json();

                if (res.status === 200) {
                    showAlert("Check Mailtrap for Step-Up OTP");

                    loginStep = 3;

                    document.getElementById("otp-1").classList.add("hidden");
                    document.getElementById("otp-2").classList.remove("hidden");
                    document.getElementById("login-btn").textContent = "Verify Step-Up OTP";
                } else {
                    showAlert(data.error, true);
                }
            }

            else if (loginStep === 3) {
                const res = await fetch(`${API_BASE}/auth/login-scenario-3/step3`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username,
                        otp: otp2
                    })
                });

                processLoginResponse(await res.json(), res.status);
            }
        }

    } catch (err) {
        console.error(err);
        showAlert("Server connection failed.", true);
    }
}

// LOGIN RESPONSE
function processLoginResponse(data, status) {
    if (status === 200 && data.session_token) {
        localStorage.setItem("session_token", data.session_token);

        document.getElementById("user-name-display").textContent = data.username;
        document.getElementById("user-role-badge").textContent = data.role;

        document.getElementById("login-view").classList.add("hidden");
        document.getElementById("dashboard-view").classList.remove("hidden");

        showAlert("Login Successful");
    } else {
        showAlert(data.error || "Authentication failed", true);
    }
}

// LOGOUT
async function logout() {
    const token = localStorage.getItem("session_token");

    try {
        if (token) {
            await fetch(`${API_BASE}/auth/logout`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`
                }
            });
        }
    } catch (err) {
        console.error(err);
    }

    localStorage.removeItem("session_token");

    document.getElementById("dashboard-view").classList.add("hidden");
    document.getElementById("login-view").classList.remove("hidden");

    switchTab("scenario-1");

    document.getElementById("username").value = "";
    document.getElementById("password").value = "";

    showAlert("Logged out successfully");
}

// DASHBOARD DATA
async function fetchResource(resourceName) {
    document.getElementById("content-title").textContent =
        resourceName.replace("_", " ").toUpperCase();

    const token = localStorage.getItem("session_token");

    try {
        const res = await fetch(`${API_BASE}/portal/${resourceName}`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        if (res.status === 401) {
            showAlert("Session expired. Please log in again.", true);

            localStorage.removeItem("session_token");

            document.getElementById("dashboard-view").classList.add("hidden");
            document.getElementById("login-view").classList.remove("hidden");

            return;
        }

        if (res.status === 403) {
            document.getElementById("content-body").innerHTML = `
                <div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4">
                    <p class="font-bold">403 Forbidden - Access Denied</p>
                    <p>RBAC Violation: Your current role does not have permission to view this module.</p>
                </div>
            `;

            showAlert("Access Denied", true);
            return;
        }

        if (res.status === 200) {
            const data = await res.json();

            document.getElementById("content-body").innerHTML = `
                <pre class="bg-gray-100 p-4 rounded text-sm overflow-x-auto">${JSON.stringify(
                    data,
                    null,
                    2
                )}</pre>
            `;

            return;
        }

        document.getElementById("content-body").innerHTML =
            `<p class="text-gray-500">Error: Status ${res.status}</p>`;

    } catch (err) {
        console.error(err);

        document.getElementById("content-body").innerHTML =
            `<p class="text-gray-500">Could not reach endpoint.</p>`;
    }
}

// SECURITY AUDIT LOGS
async function fetchLogs() {
    document.getElementById("content-title").textContent =
        "SECURITY AUDIT LOGS";

    const token = localStorage.getItem("session_token");

    try {
        const res = await fetch(`${API_BASE}/logs/`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        if (res.status === 403) {
            document.getElementById("content-body").innerHTML = `
                <div class="bg-red-100 border-l-4 border-red-500 text-red-700 p-4">
                    <p class="font-bold">Access Denied</p>
                    <p>Only Administrators can view security logs.</p>
                </div>
            `;

            return;
        }

        if (res.status === 200) {
            const logs = await res.json();

            let html = `
                <table class="min-w-full text-left text-sm whitespace-nowrap">
                    <thead class="border-b-2 border-gray-200">
                        <tr>
                            <th class="px-4 py-2">Timestamp</th>
                            <th class="px-4 py-2">User</th>
                            <th class="px-4 py-2">Action</th>
                            <th class="px-4 py-2">Status</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            logs.forEach(log => {
                const statusColor =
                    log.status === "SUCCESS"
                        ? "text-green-600"
                        : log.status === "LOCKED"
                        ? "text-orange-600"
                        : "text-red-600";

                html += `
                    <tr class="border-b">
                        <td class="px-4 py-2">${log.timestamp}</td>
                        <td class="px-4 py-2">${log.username} (${log.role})</td>
                        <td class="px-4 py-2">${log.scenario} - ${log.action}</td>
                        <td class="px-4 py-2 font-bold ${statusColor}">
                            ${log.status}
                        </td>
                    </tr>
                `;
            });

            html += `
                    </tbody>
                </table>
            `;

            document.getElementById("content-body").innerHTML = html;
            return;
        }

        document.getElementById("content-body").innerHTML =
            `<p class="text-gray-500">Error: Status ${res.status}</p>`;

    } catch (err) {
        console.error(err);

        document.getElementById("content-body").innerHTML =
            `<p class="text-gray-500">Could not fetch logs.</p>`;
    }
}