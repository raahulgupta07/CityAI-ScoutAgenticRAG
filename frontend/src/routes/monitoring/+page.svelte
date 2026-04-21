<script lang="ts">
	import { onMount } from 'svelte';
	import { getAuthHeaders } from '$lib/api';

	let loading = $state(true);
	let stats = $state<any>({});
	let tenants = $state<any[]>([]);
	let liveQueries = $state<any[]>([]);
	let usage = $state<any>({});
	let alerts = $state<any[]>([]);
	let auditLog = $state<any[]>([]);

	onMount(async () => {
		await Promise.all([loadStats(), loadTenants(), loadLiveQueries(), loadUsage(), loadAlerts(), loadAudit()]);
		loading = false;
		// Auto-refresh live queries every 10s
		setInterval(loadLiveQueries, 10000);
	});

	async function loadStats() {
		try { stats = await (await fetch('/api/super/stats', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadTenants() {
		try { tenants = await (await fetch('/api/super/tenants', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadLiveQueries() {
		try { liveQueries = await (await fetch('/api/super/monitoring/live-queries?limit=15', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadUsage() {
		try { usage = await (await fetch('/api/super/monitoring/usage?days=30', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadAlerts() {
		try { alerts = await (await fetch('/api/super/monitoring/alerts?unread=true', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadAudit() {
		try { auditLog = await (await fetch('/api/super/monitoring/audit?limit=30', { headers: getAuthHeaders() })).json(); } catch {}
	}

	function openDeepDive(tenantId: string) {
		window.location.href = `/monitoring/${tenantId}`;
	}

	function timeAgo(dateStr: string) {
		if (!dateStr) return '';
		const d = new Date(dateStr);
		const s = Math.floor((Date.now() - d.getTime()) / 1000);
		if (s < 60) return `${s}s ago`;
		if (s < 3600) return `${Math.floor(s/60)}m ago`;
		if (s < 86400) return `${Math.floor(s/3600)}h ago`;
		return `${Math.floor(s/86400)}d ago`;
	}

	const healthItems = $derived([
		{ label: 'Database', icon: 'database', status: stats.db_status || 'ok', detail: `${stats.db_size_mb || 0}MB` },
		{ label: 'PgVector', icon: 'rebase_edit', status: 'ok', detail: `${stats.total_embeddings || 0} vectors` },
		{ label: 'LLM Engine', icon: 'psychology', status: 'ok', detail: `${usage.avg_duration_ms || 0}ms avg` },
		{ label: 'Storage', icon: 'storage', status: 'ok', detail: `${stats.storage_mb || 0}MB` },
	]);
</script>

<style>
	* { border-radius: 0px !important; }

	.ink-border {
		border-style: solid;
		border-color: #383832;
		border-width: 2px 4px 4px 2px;
	}

	.stamp-shadow {
		box-shadow: 4px 4px 0px 0px #383832;
	}

	.tag-label {
		background: #383832;
		color: #feffd6;
		font-size: 10px;
		font-weight: 900;
		text-transform: uppercase;
		padding: 2px 8px;
		display: inline-block;
	}

	.dark-title-bar {
		background: #383832;
		color: #feffd6;
		font-weight: 900;
		text-transform: uppercase;
		padding: 12px 20px;
		font-family: 'Space Grotesk', sans-serif;
	}

	.section-animate > * {
		animation: slideUp 0.4s ease-out both;
	}
	.section-animate > *:nth-child(1) { animation-delay: 0.0s; }
	.section-animate > *:nth-child(2) { animation-delay: 0.07s; }
	.section-animate > *:nth-child(3) { animation-delay: 0.14s; }
	.section-animate > *:nth-child(4) { animation-delay: 0.21s; }
	.section-animate > *:nth-child(5) { animation-delay: 0.28s; }
	.section-animate > *:nth-child(6) { animation-delay: 0.35s; }
	.section-animate > *:nth-child(7) { animation-delay: 0.42s; }
	.section-animate > *:nth-child(8) { animation-delay: 0.49s; }

	@keyframes slideUp {
		from { opacity: 0; transform: translateY(18px); }
		to { opacity: 1; transform: translateY(0); }
	}
</style>

{#if loading}
	<div class="flex items-center justify-center h-64" style="background:#feffd6">
		<span class="material-symbols-outlined text-4xl" style="color:#383832; animation: pulse 1.5s infinite">hourglass_empty</span>
	</div>
{:else}
<div class="section-animate pt-6 space-y-8 pb-12" style="background:#feffd6; min-height:100vh; padding-left:24px; padding-right:24px; font-family:'Space Grotesk', sans-serif;">

	<!-- Chapter Heading -->
	<div>
		<div class="dark-title-bar flex items-center gap-3">
			<span class="material-symbols-outlined" style="color:#ff9d00; font-size:22px; font-variation-settings:'FILL' 1">monitoring</span>
			<span class="text-lg tracking-wide">Command Center</span>
		</div>
		<div style="background:#383832; padding:8px 20px; border-bottom:4px solid #ff9d00;">
			<span style="font-family:monospace; color:#00fc40; font-size:13px;">How is the platform performing right now?</span>
		</div>
		<div class="flex items-center gap-4 mt-3">
			<p class="text-sm font-bold uppercase" style="color:#65655e; letter-spacing:0.08em;">Real-time platform monitoring and tenant intelligence</p>
			<div class="flex items-center gap-2 ml-auto">
				<div class="flex items-center gap-2 px-3 py-1.5 ink-border" style="background:white;">
					<span class="w-2.5 h-2.5" style="background:#007518; animation: pulse 1.5s infinite"></span>
					<span class="text-[10px] font-black uppercase tracking-widest" style="color:#383832">Live</span>
				</div>
				{#if alerts.length > 0}
					<span class="tag-label">{alerts.length} alerts</span>
				{/if}
			</div>
		</div>
	</div>

	<!-- Hero Metrics -->
	<div class="grid grid-cols-5 gap-4">
		{#each [
			{ label: 'Tenants', value: tenants.length, sub: `${tenants.filter(t => t.is_active).length} active` },
			{ label: 'Documents', value: stats.total_documents || 0, sub: `${stats.total_embeddings || 0} embeddings` },
			{ label: 'Queries (30d)', value: stats.total_queries || 0, sub: `+${stats.total_queries_24h || 0} today` },
			{ label: 'LLM Cost (30d)', value: `$${(usage.total_cost_usd || 0).toFixed(2)}`, sub: `${usage.total_operations || 0} operations`, highlight: true },
			{ label: 'DB Size', value: `${stats.db_size_mb || 0}`, valueSuffix: 'MB', sub: `${stats.storage_mb || 0}MB files` },
		] as metric}
			<div class="p-5 ink-border stamp-shadow" style="background:white;">
				<p class="text-[10px] uppercase tracking-widest font-black" style="color:#65655e">{metric.label}</p>
				<p class="text-3xl font-black mt-2" style="color:{metric.highlight ? '#006f7c' : '#383832'}; font-family:'Space Grotesk', sans-serif;">
					{metric.value}{#if metric.valueSuffix}<span class="text-lg">{metric.valueSuffix}</span>{/if}
				</p>
				<p class="text-xs mt-1 font-bold" style="color:#65655e">{metric.sub}</p>
			</div>
		{/each}
	</div>

	<!-- System Health -->
	<div class="grid grid-cols-4 gap-4">
		{#each healthItems as h}
			<div class="p-4 flex items-center gap-3 ink-border" style="background:white; border-left:4px solid {h.status === 'ok' ? '#007518' : '#be2d06'}">
				<span class="material-symbols-outlined" style="color:{h.status === 'ok' ? '#007518' : '#be2d06'}; font-variation-settings:'FILL' 1">{h.icon}</span>
				<div>
					<p class="text-xs font-black uppercase" style="color:#383832">{h.label}</p>
					<p class="text-[10px] font-bold" style="color:#65655e">
						{#if h.status === 'ok'}
							<span style="color:#007518">Online</span>
						{:else}
							<span style="color:#be2d06">{h.status}</span>
						{/if}
						 &middot; {h.detail}
					</p>
				</div>
			</div>
		{/each}
	</div>

	<div class="grid grid-cols-12 gap-6">
		<!-- Live Query Stream (8 cols) -->
		<div class="col-span-8 ink-border stamp-shadow overflow-hidden" style="background:white;">
			<div class="dark-title-bar flex justify-between items-center">
				<div class="flex items-center gap-2">
					<span class="w-2.5 h-2.5" style="background:#00fc40; animation: pulse 1.5s infinite"></span>
					<span>Live Query Stream</span>
				</div>
				<span class="text-[10px] font-mono" style="color:#feffd6; opacity:0.7;">Auto-refresh 10s</span>
			</div>
			<div>
				{#each liveQueries.slice(0, 10) as q, i}
					<div class="px-5 py-3 flex items-center gap-4" style="background:{i % 2 === 0 ? 'white' : '#fcf9ef'}; border-bottom:1px solid #ebe8dd;">
						<span class="text-[10px] font-mono w-14 flex-shrink-0" style="color:#65655e">{timeAgo(q.created_at)}</span>
						<span class="tag-label">{q.tenant}</span>
						<span class="text-sm flex-1 truncate font-bold" style="color:#383832">{q.question}</span>
						<span class="text-[10px] font-mono font-bold" style="color:#006f7c">{q.duration}s</span>
						{#if q.feedback === 'up'}
							<span class="material-symbols-outlined text-sm" style="color:#007518; font-variation-settings:'FILL' 1">thumb_up</span>
						{:else if q.feedback === 'down'}
							<span class="material-symbols-outlined text-sm" style="color:#be2d06; font-variation-settings:'FILL' 1">thumb_down</span>
						{:else}
							<span class="w-4"></span>
						{/if}
					</div>
				{:else}
					<div class="px-6 py-8 text-center font-bold uppercase text-sm" style="color:#65655e">No queries yet</div>
				{/each}
			</div>
		</div>

		<!-- Cost Breakdown + Alerts (4 cols) -->
		<div class="col-span-4 space-y-6">
			<!-- Cost by Operation -->
			<div class="ink-border stamp-shadow overflow-hidden" style="background:white;">
				<div class="dark-title-bar text-sm flex items-center gap-2">
					<span class="material-symbols-outlined text-base" style="color:#ff9d00; font-variation-settings:'FILL' 1">payments</span>
					Cost by Operation
				</div>
				<div class="p-5">
					{#each (usage.by_operation || []).slice(0, 5) as op}
						<div class="flex justify-between items-center py-1.5" style="border-bottom:1px solid #ebe8dd;">
							<span class="text-xs font-bold uppercase" style="color:#383832">{op.operation}</span>
							<div class="flex items-center gap-3">
								<span class="text-[10px] font-mono font-bold" style="color:#65655e">{op.count}x</span>
								<span class="text-xs font-black" style="color:#006f7c">${(op.cost || 0).toFixed(3)}</span>
							</div>
						</div>
					{:else}
						<p class="text-xs font-bold uppercase" style="color:#65655e">No usage data yet</p>
					{/each}
				</div>
			</div>

			<!-- Alerts -->
			<div class="ink-border stamp-shadow overflow-hidden" style="background:white;">
				<div class="dark-title-bar text-sm flex items-center gap-2">
					<span class="material-symbols-outlined text-base" style="color:#ff9d00; font-variation-settings:'FILL' 1">notifications</span>
					Alerts ({alerts.length})
				</div>
				<div class="p-5">
					{#each alerts.slice(0, 5) as a}
						<div class="py-2 flex items-start gap-2" style="border-bottom:1px solid #ebe8dd;">
							<span class="w-2.5 h-2.5 mt-1 flex-shrink-0" style="background:{a.severity === 'critical' ? '#be2d06' : a.severity === 'warning' ? '#ff9d00' : '#006f7c'}"></span>
							<div>
								<p class="text-xs font-black uppercase" style="color:#383832">{a.title}</p>
								<p class="text-[10px] font-bold" style="color:#65655e">{timeAgo(a.created_at)}</p>
							</div>
						</div>
					{:else}
						<p class="text-xs font-bold" style="color:#007518">No active alerts</p>
					{/each}
				</div>
			</div>
		</div>
	</div>

	<!-- Tenant Table -->
	<div class="ink-border stamp-shadow overflow-hidden" style="background:white;">
		<div class="dark-title-bar flex items-center gap-2">
			<span class="material-symbols-outlined text-base" style="color:#ff9d00; font-variation-settings:'FILL' 1">groups</span>
			Tenant Overview
		</div>
		<table class="w-full text-left">
			<thead>
				<tr style="background:#ebe8dd; border-bottom:2px solid #383832;">
					<th class="px-6 py-3 text-[10px] uppercase tracking-widest font-black" style="color:#383832">Tenant</th>
					<th class="px-6 py-3 text-[10px] uppercase tracking-widest font-black" style="color:#383832">Mode</th>
					<th class="px-6 py-3 text-[10px] uppercase tracking-widest font-black" style="color:#383832">Status</th>
					<th class="px-6 py-3 text-[10px] uppercase tracking-widest font-black text-right" style="color:#383832">Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each tenants as t, i}
					<tr class="cursor-pointer transition-colors hover:!bg-[#ebe8dd]" onclick={() => openDeepDive(t.id)} style="background:{i % 2 === 0 ? 'white' : '#fcf9ef'}; border-bottom:1px solid #ebe8dd;">
						<td class="px-6 py-4">
							<div class="font-black text-sm uppercase" style="color:#383832">{t.name}</div>
							<div class="text-[10px] font-bold" style="color:#65655e">{t.id} &middot; {t.agent_name || 'Agent'}</div>
						</td>
						<td class="px-6 py-4">
							<span class="tag-label">{(t.document_mode || 'general').toUpperCase()}</span>
						</td>
						<td class="px-6 py-4">
							<div class="flex items-center gap-2">
								<span class="w-2.5 h-2.5" style="background:{t.is_active ? '#007518' : '#65655e'}"></span>
								<span class="text-xs font-black uppercase" style="color:{t.is_active ? '#007518' : '#65655e'}">{t.is_active ? 'Active' : 'Inactive'}</span>
							</div>
						</td>
						<td class="px-6 py-4 text-right">
							<button onclick={(e) => { e.stopPropagation(); openDeepDive(t.id); }}
								class="text-[10px] font-black uppercase px-4 py-1.5 cursor-pointer ink-border stamp-shadow active:translate-x-[2px] active:translate-y-[2px] transition-transform"
								style="background:#00fc40; color:#383832;">
								Deep Dive
							</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Audit Trail -->
	<div class="ink-border stamp-shadow overflow-hidden" style="background:white;">
		<div class="dark-title-bar flex items-center gap-2">
			<span class="material-symbols-outlined text-base" style="color:#ff9d00; font-variation-settings:'FILL' 1">history</span>
			Audit Trail (Recent)
		</div>
		<div>
			{#each auditLog.slice(0, 15) as log, i}
				<div class="px-6 py-3 flex items-center gap-4" style="background:{i % 2 === 0 ? 'white' : '#fcf9ef'}; border-bottom:1px solid #ebe8dd;">
					<span class="text-[10px] font-mono font-bold w-14 flex-shrink-0" style="color:#65655e">{timeAgo(log.created_at)}</span>
					<span class="tag-label">{log.action}</span>
					<span class="text-xs flex-1 truncate font-bold" style="color:#383832">{log.details || log.resource_id || ''}</span>
					<span class="text-[10px] font-bold uppercase" style="color:#65655e">{log.tenant_id}</span>
				</div>
			{:else}
				<div class="px-6 py-8 text-center font-bold uppercase text-sm" style="color:#65655e">No audit events yet</div>
			{/each}
		</div>
	</div>
</div>

{/if}
