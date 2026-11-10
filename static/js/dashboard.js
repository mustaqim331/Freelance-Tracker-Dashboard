let weeklyChartObj = null, earningsChartObj = null, hoursChartObj = null, dailyTrendChartObj = null;
let globalTasks = [], globalDashboardData = null;
const $ = id => document.getElementById(id);

document.addEventListener("DOMContentLoaded", () => {
    const today = new Date().toLocaleDateString("en-CA");
    if ($("currentDateLabel")) $("currentDateLabel").innerText = today;
    if ($("newTaskDate")) $("newTaskDate").value = today;
    loadData();
    loadTasks();
});

async function api(url, method = "GET", body = null) {
    const options = { method, headers: {} };
    if (body instanceof FormData) options.body = body;
    else if (body !== null) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Request failed");
    return result;
}

function showLoading(message) {
    if ($("loadingText")) $("loadingText").innerText = message;
    if ($("loadingOverlay")) $("loadingOverlay").style.display = "flex";
}
function hideLoading() {
    if ($("loadingOverlay")) $("loadingOverlay").style.display = "none";
}
function formatAsHoursMinsDot(value) {
    const n = Number(value) || 0;
    const hrs = Math.floor(n);
    const mins = Math.round((n - hrs) * 60);
    return `${hrs}.${String(mins).padStart(2, "0")}`;
}
async function loadData() {
    try {
        globalDashboardData = await api("/api/dashboard");
        renderDashboard(globalDashboardData);
        updateTodayFocusSection();
    } catch (e) { alert(e.message); }
}
async function loadTasks() {
    try {
        globalTasks = await api("/api/tasks");
        renderTasks(globalTasks);
        updateTodayFocusSection();
    } catch (e) { alert(e.message); }
}
function updateTodayFocusSection() {
    if (!globalDashboardData) return;
    const today = new Date().toLocaleDateString("en-CA");
    const settings = globalDashboardData.settings;
    const target = Number(settings.dailyHoursTarget) || 3;
    const day = globalDashboardData.dailyBreakdown.find(d => d.date === today);
    const hours = day ? Number(day.hours) : 0;
    const earnings = day ? Number(day.earnings) : 0;
    if ($("currentDateLabel")) $("currentDateLabel").innerText = today;
    if ($("lblTodayEarnings")) $("lblTodayEarnings").innerText = `RM ${earnings.toFixed(2)}`;
    if ($("lblTodayHours")) $("lblTodayHours").innerText = `${formatAsHoursMinsDot(hours)} / ${target.toFixed(2)}`;
    const remaining = target - hours;
    if ($("lblRemainingLabel")) $("lblRemainingLabel").innerText = remaining >= 0 ? "Remaining" : "Exceeded By";
    if ($("lblTodayRemaining")) $("lblTodayRemaining").innerText = formatAsHoursMinsDot(Math.abs(remaining));
    const start = new Date(2026, 10, 1);
    const now = new Date(); now.setHours(0,0,0,0);
    const elapsed = Math.floor((now - start) / 86400000);
    if ($("lblDaysLeft")) $("lblDaysLeft").innerText = Math.max(0, 6 - (elapsed % 7));
    if ($("todayHeading")) $("todayHeading").innerText = `${hours >= target ? "🟢 Goal Achieved!" : "🔴 Today's Focus"} (${today})`;
    if ($("todayFocusCard")) $("todayFocusCard").className = `card p-3 p-md-4 mb-3 mb-md-4 border-${hours >= target ? "success" : "danger"} border-3 bg-white`;
    const tbody = $("todayTaskTableBody");
    if (!tbody) return;
    const todayTasks = globalTasks.filter(t => t.date === today);
    tbody.innerHTML = todayTasks.length ? todayTasks.map(t => taskRow(t, true)).join("") :
        '<tr><td colspan="4" class="text-center text-muted">No tasks scheduled for today yet.</td></tr>';
}
function taskRow(t, compact = false) {
    const color = t.category === "Work" ? "primary" : (t.category === "Study" ? "info" : "secondary");
    const status = t.status === "Completed" ? "success" : "warning text-dark";
    return `<tr><td><strong>${escapeHtml(t.name)}</strong></td>
      <td><span class="badge bg-${color}">${escapeHtml(t.category)}</span></td>
      ${compact ? "" : `<td>${escapeHtml(t.date)}</td>`}
      <td>${Number(t.hours).toFixed(1)} hrs</td>
      <td><span class="badge bg-${status}" style="cursor:pointer" onclick="toggleTask(${t.id})">${t.status} 🔄</span></td></tr>`;
}
function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function renderTasks(tasks) {
    const tbody = $("taskTableBody");
    if (tbody) tbody.innerHTML = tasks.length ? tasks.map(t => taskRow(t)).join("") :
        '<tr><td colspan="5" class="text-center text-muted">No tasks added yet.</td></tr>';
}
function renderDashboard(data) {
    $("lblTotalEarnings").innerText = "RM " + data.totalEarnings;
    $("lblTotalHours").innerText = formatAsHoursMinsDot(data.totalHours) + " hrs";
    $("txtDailyHours").value = data.settings.dailyHoursTarget;
    $("txtWeeklyEarn").value = data.settings.weeklyEarningsTarget;
    $("txtMonthlyEarn").value = data.settings.monthlyEarningsTarget;
    $("txtMonthlyHours").value = data.settings.monthlyHoursTarget;

    const donutOptions = { responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{position:"bottom"}, datalabels:{color:"#fff",font:{weight:"bold"}} } };
    function donut(canvasId, old, labels, values, colors) {
        if (old) old.destroy();
        return new Chart($(canvasId), {type:"doughnut", data:{labels,datasets:[{data:values,backgroundColor:colors}]},options:donutOptions});
    }
    weeklyChartObj = donut("weeklyChart", weeklyChartObj, ["This Week","Remaining"],
        [Number(data.currentWeeklyEarnings),Math.max(0,Number(data.settings.weeklyEarningsTarget)-Number(data.currentWeeklyEarnings))],["#9b59b6","#e0e0e0"]);
    earningsChartObj = donut("earningsChart", earningsChartObj, ["Earned","Remaining"],
        [Number(data.totalEarnings),Math.max(0,Number(data.settings.monthlyEarningsTarget)-Number(data.totalEarnings))],["#2ecc71","#e0e0e0"]);
    hoursChartObj = donut("hoursChart", hoursChartObj, ["Completed","Remaining"],
        [Number(data.totalHours),Math.max(0,Number(data.settings.monthlyHoursTarget)-Number(data.totalHours))],["#3498db","#e0e0e0"]);
    if (dailyTrendChartObj) dailyTrendChartObj.destroy();
    const dailyTarget = Number(data.settings.dailyHoursTarget) || 3;
    dailyTrendChartObj = new Chart($("dailyTrendChart"), {type:"bar",
        data:{labels:data.dailyBreakdown.map(d=>d.date),datasets:[{label:"Hours Worked",
            data:data.dailyBreakdown.map(d=>Number(d.hours)),
            backgroundColor:data.dailyBreakdown.map(d=>Number(d.hours)>=dailyTarget?"#3498db":"#e74c3c"),borderRadius:6}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
            scales:{y:{beginAtZero:true}}}});
    const accordion = $("accordionDaily");
    if (accordion) accordion.innerHTML = data.dailyBreakdown.slice().reverse().map((d,i) => {
        const items = d.items.length ? d.items.map(item =>
            `<li class="list-group-item d-flex justify-content-between"><div><strong>${escapeHtml(item.time)}</strong> - <span class="badge bg-secondary">${escapeHtml(item.location)}</span></div><span>${escapeHtml(item.durationFormatted)}</span></li>`
        ).join("") : '<li class="list-group-item text-muted text-center">Rest day / No recordings logged.</li>';
        const h = Number(d.hours), badge = h >= dailyTarget ? "success" : (h > 0 ? "warning text-dark" : "danger");
        return `<div class="accordion-item"><h2 class="accordion-header" id="heading${i}">
          <button class="accordion-button ${i ? "collapsed":""} p-2" type="button" data-bs-toggle="collapse" data-bs-target="#collapse${i}">
          <div class="d-flex justify-content-between w-100 me-2 small"><span><strong>📅 ${d.date}</strong> (${d.count})</span>
          <span><span class="badge bg-${badge}">⏱️ ${formatAsHoursMinsDot(h)}</span> | <strong class="text-success">RM ${d.earnings}</strong></span></div></button></h2>
          <div id="collapse${i}" class="accordion-collapse collapse ${i===0?"show":""}" data-bs-parent="#accordionDaily">
          <div class="accordion-body p-2"><ul class="list-group list-group-flush">${items}</ul></div></div></div>`;
    }).join("");
}
async function addNewTask() {
    const payload = {name:$("newTaskName").value,category:$("newTaskCat").value,
        date:$("newTaskDate").value,hours:$("newTaskHours").value};
    try {
        await api("/api/tasks","POST",payload);
        bootstrap.Modal.getInstance($("taskModal")).hide();
        $("newTaskName").value = "";
        await loadTasks();
    } catch(e) { alert(e.message); }
}
async function toggleTask(id) {
    try { await api(`/api/tasks/${id}/toggle`,"POST"); await loadTasks(); }
    catch(e) { alert(e.message); }
}
async function saveTargets() {
    try {
        globalDashboardData = await api("/api/settings","POST",{
            dailyHours:$("txtDailyHours").value,weeklyEarn:$("txtWeeklyEarn").value,
            monthlyEarn:$("txtMonthlyEarn").value,monthlyHours:$("txtMonthlyHours").value
        });
        renderDashboard(globalDashboardData); updateTodayFocusSection();
        bootstrap.Modal.getInstance($("targetModal")).hide();
    } catch(e) { alert(e.message); }
}
async function uploadFile() {
    const input = $("imgUploader");
    if (!input.files.length) return;
    showLoading(`Reading ${input.files.length} screenshot${input.files.length === 1 ? "" : "s"} with local OCR...`);
    try {
        const form = new FormData();
        Array.from(input.files).forEach(file => form.append("image", file));
        const result = await api("/api/upload","POST",form);
        const failures = (result.imageResults || [])
            .filter(image => image.error)
            .map(image => `${image.filename}: ${image.error}`);
        const summary = `${result.imageResults.length} images processed.\nDetected: ${result.detectedCount}\nAdded: ${result.addedCount}\nDuplicates skipped: ${result.duplicateCount}`;
        alert(failures.length ? `${summary}\n\nSome images could not be processed:\n${failures.join("\n")}` : summary);
        input.value = "";
        await loadData();
    } catch(e) { alert("Image processing failed: "+e.message); input.value=""; }
    finally { hideLoading(); }
}
