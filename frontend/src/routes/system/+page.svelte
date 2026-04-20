<script lang="ts">
	import { onMount } from 'svelte';
	import { getAuthHeaders } from '$lib/api';

	let loading = $state(true);
	let schemas = $state<any[]>([]);
	let health = $state<any>({});
	let stats = $state<any>({});
	let expandedSchema = $state('');

	onMount(async () => {
		await Promise.all([loadSchemas(), loadHealth(), loadStats()]);
		loading = false;
	});

	async function loadSchemas() {
		try { schemas = await (await fetch('/api/super/schemas', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadHealth() {
		try { health = await (await fetch('/api/super/health', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadStats() {
		try { stats = await (await fetch('/api/super/stats', { headers: getAuthHeaders() })).json(); } catch {}
	}

	const healthCards = $derived([
		{ key: 'database', icon: 'database', label: 'Database' },
		{ key: 'pgvector', icon: 'rebase_edit', label: 'PgVector' },
		{ key: 'llm', icon: 'psychology', label: 'LLM Engine' },
		{ key: 'disk', icon: 'storage', label: 'Disk Volume' },
	]);
</script>

<div class="pt-6 section-animate" style="display:flex;flex-direction:column;gap:3rem;">

	<!-- HERO STATUS CARDS -->
	<div class="grid grid-cols-12 gap-6">
		<div class="col-span-12 lg:col-span-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
			{#each healthCards as card}
				{@const h = (health[card.key] || {}) as any}
				{@const statusText = h.status === 'ok' ? (card.key === 'database' ? 'Reachable' : card.key === 'pgvector' ? 'Active' : card.key === 'llm' ? 'Connected' : 'Healthy') : h.status || 'Unknown'}
				{@const statusColor = h.status === 'ok' ? '#007518' : h.status === 'warning' ? '#ff9d00' : '#be2d06'}
				<div class="ink-border stamp-shadow bg-white p-5">
					<div class="flex items-start justify-between mb-4">
						<span class="material-symbols-outlined text-2xl" style="color:#383832">{card.icon}</span>
						<span class="flex h-3 w-3 {h.status === 'ok' ? 'animate-pulse' : ''}" style="background:{statusColor};border:2px solid #383832"></span>
					</div>
					<p class="tag-label mb-2">{card.label}</p>
					<p class="text-xl font-black" style="color:#383832">{statusText}</p>
					<div class="mt-3 h-2 w-full overflow-hidden" style="background:#ebe8dd;border:1px solid #383832">
						<div class="h-full" style="background:{statusColor};width:{h.status === 'ok' ? '100' : h.status === 'warning' ? '60' : '20'}%"></div>
					</div>
				</div>
			{/each}
		</div>

		<!-- System Audit Card -->
		<div class="col-span-12 lg:col-span-4 ink-border stamp-shadow bg-white flex flex-col justify-between">
			<div class="dark-title-bar flex items-center gap-2">
				<span class="material-symbols-outlined text-sm" style="color:#feffd6">monitor_heart</span>
				SYSTEM AUDIT
			</div>
			<div class="p-6 flex flex-col justify-between flex-1">
				<p class="text-sm mb-6" style="color:#65655e">Infrastructure health monitoring and diagnostics.</p>
				<div class="space-y-3 text-sm">
					<div class="flex justify-between pb-2" style="border-bottom:1px solid #ebe8dd">
						<span class="font-black uppercase text-xs" style="color:#65655e">Uptime</span>
						<span class="font-mono font-black" style="color:#383832">{stats.uptime || '---'}</span>
					</div>
					<div class="flex justify-between pb-2" style="border-bottom:1px solid #ebe8dd">
						<span class="font-black uppercase text-xs" style="color:#65655e">Tenants</span>
						<span class="font-mono font-black" style="color:#383832">{stats.total_tenants || 0}</span>
					</div>
					<div class="flex justify-between">
						<span class="font-black uppercase text-xs" style="color:#65655e">Schemas</span>
						<span class="font-mono font-black" style="color:#383832">{schemas.length} + public</span>
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- DATABASE INFRASTRUCTURE -->
	<div style="display:flex;flex-direction:column;gap:1.5rem;">
		<div class="flex items-center gap-3">
			<span class="material-symbols-outlined text-2xl" style="color:#383832">database</span>
			<h2 class="font-black text-2xl tracking-tight uppercase" style="color:#383832">Database Infrastructure</h2>
		</div>

		<div class="grid grid-cols-12 gap-6">
			<!-- Technical Specs -->
			<div class="col-span-12 lg:col-span-4 space-y-4">
				<div class="ink-border stamp-shadow bg-white">
					<div class="dark-title-bar">Technical Specs</div>
					<div class="p-6 space-y-6">
						<div>
							<p class="tag-label mb-3">Database Engine</p>
							<div class="flex items-center gap-3">
								<div class="w-10 h-10 flex items-center justify-center ink-border" style="background:#ebe8dd">
									<span class="material-symbols-outlined" style="color:#383832">database</span>
								</div>
								<div>
									<p class="font-black" style="color:#383832">PostgreSQL 18</p>
									<p class="text-xs flex items-center gap-1" style="color:#007518">
										<span class="material-symbols-outlined text-xs">add_circle</span>
										PgVector {health.pgvector?.detail || ''} Enabled
									</p>
								</div>
							</div>
						</div>

						<div class="grid grid-cols-2 gap-4">
							<div class="p-4 ink-border" style="background:#fcf9ef">
								<p class="font-black uppercase text-[10px] tracking-widest mb-1" style="color:#65655e">Total Size</p>
								<p class="text-xl font-black" style="color:#006f7c">{stats.db_size_mb || 0} MB</p>
							</div>
							<div class="p-4 ink-border" style="background:#fcf9ef">
								<p class="font-black uppercase text-[10px] tracking-widest mb-1" style="color:#65655e">File Storage</p>
								<p class="text-xl font-black" style="color:#006f7c">{stats.storage_mb || 0} MB</p>
							</div>
						</div>

						<div>
							<p class="tag-label mb-3">Schema Breakdown</p>
							<div class="space-y-1">
								<div class="flex justify-between items-center text-sm p-2" style="color:#65655e;border-bottom:1px solid #ebe8dd">
									<span class="flex items-center gap-2">
										<span class="material-symbols-outlined text-sm">groups</span>
										<span class="font-black uppercase text-xs">Tenants</span>
									</span>
									<span class="font-mono font-black" style="color:#383832">{schemas.length}</span>
								</div>
								<div class="flex justify-between items-center text-sm p-2" style="color:#65655e">
									<span class="flex items-center gap-2">
										<span class="material-symbols-outlined text-sm">public</span>
										<span class="font-black uppercase text-xs">Public</span>
									</span>
									<span class="font-mono font-black" style="color:#383832">1</span>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- Tenant Schemas -->
			<div class="col-span-12 lg:col-span-8">
				{#if schemas.length === 0}
					<div class="min-h-[400px] ink-border stamp-shadow bg-white flex flex-col items-center justify-center p-12 text-center">
						<div class="w-32 h-32 flex items-center justify-center mb-6 mx-auto ink-border" style="background:#ebe8dd">
							<span class="material-symbols-outlined text-6xl" style="color:#65655e">layers_clear</span>
						</div>
						<h3 class="font-black text-2xl mb-2 uppercase" style="color:#383832">No Active Tenant Schemas</h3>
						<p class="max-w-sm mx-auto mb-8 text-sm" style="color:#65655e">Your system infrastructure is ready. Provision your first tenant to begin data isolation and environment scaling.</p>
						<a href="/"
							class="px-6 py-2.5 text-sm font-black inline-flex items-center gap-2 cursor-pointer ink-border stamp-shadow-sm uppercase tracking-wider"
							style="background:#383832;color:#feffd6">
							<span class="material-symbols-outlined text-sm">add</span>
							PROVISION NEW TENANT
						</a>
					</div>
				{:else}
					<div class="ink-border stamp-shadow bg-white overflow-hidden">
						<div class="dark-title-bar flex items-center gap-2">
							<span class="material-symbols-outlined text-sm" style="color:#feffd6">database</span>
							TENANT SCHEMAS
						</div>
						<div>
							{#each schemas as schema, idx}
								<div style="border-bottom:2px solid #ebe8dd">
									<button onclick={() => expandedSchema = expandedSchema === schema.tenant_id ? '' : schema.tenant_id}
										class="w-full flex items-center justify-between px-6 py-4 cursor-pointer transition-all"
										style="background:{idx % 2 === 0 ? '#ffffff' : '#fcf9ef'}"
										onmouseenter={(e) => e.currentTarget.style.background='#ebe8dd'}
										onmouseleave={(e) => e.currentTarget.style.background = idx % 2 === 0 ? '#ffffff' : '#fcf9ef'}>
										<div class="flex items-center gap-3">
											<span class="material-symbols-outlined" style="color:#383832">database</span>
											<div class="text-left">
												<span class="text-sm font-black" style="color:#383832">{schema.tenant_name}</span>
												<span class="text-[10px] ml-2 font-mono" style="color:#65655e">schema: {schema.tenant_id}</span>
											</div>
										</div>
										<div class="flex items-center gap-4">
											<span class="tag-label">{schema.total_rows} rows</span>
											<span class="material-symbols-outlined text-[18px] transition-transform {expandedSchema === schema.tenant_id ? 'rotate-180' : ''}" style="color:#383832">expand_more</span>
										</div>
									</button>
									{#if expandedSchema === schema.tenant_id}
										<div class="px-6 py-4" style="background:#ebe8dd;border-top:2px solid #383832">
											<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
												{#each schema.tables as table}
													<div class="p-3 ink-border" style="background:#ffffff">
														<span class="text-[10px] font-mono block font-black uppercase" style="color:#65655e">{table.name}</span>
														<span class="text-lg font-black" style="color:{table.rows > 0 ? '#383832' : '#bbb9b1'}">{table.rows}</span>
													</div>
												{/each}
											</div>
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>

	<!-- LATENCY & THROUGHPUT -->
	<section class="ink-border stamp-shadow bg-white">
		<div class="dark-title-bar flex items-center justify-between">
			<div class="flex items-center gap-2">
				<span class="material-symbols-outlined text-sm" style="color:#feffd6">speed</span>
				LATENCY & THROUGHPUT
			</div>
			<div class="flex gap-2">
				<span class="tag-label" style="background:#65655e;color:#feffd6">Global Ops</span>
				<span class="tag-label" style="background:#007518;color:#ffffff">All Services Up</span>
			</div>
		</div>
		<div class="p-6">
			<p class="text-xs mb-6 uppercase font-black" style="color:#65655e">Real-time telemetry from core services</p>
			<div class="grid grid-cols-1 md:grid-cols-3 gap-8">
				<div class="space-y-2">
					<div class="flex justify-between items-end">
						<span class="font-black uppercase text-[10px] tracking-widest" style="color:#65655e">Query Response</span>
						<span class="text-sm font-mono font-black" style="color:#007518">12ms</span>
					</div>
					<div class="h-12 flex items-end gap-1">
						{#each [40, 30, 50, 45, 20, 60, 35] as h, i}
							<div class="flex-1" style="height:{h}%;background:{i === 6 ? '#007518' : '#ebe8dd'};border:1px solid #383832"></div>
						{/each}
					</div>
				</div>
				<div class="space-y-2">
					<div class="flex justify-between items-end">
						<span class="font-black uppercase text-[10px] tracking-widest" style="color:#65655e">Vector Search</span>
						<span class="text-sm font-mono font-black" style="color:#006f7c">148ms</span>
					</div>
					<div class="h-12 flex items-end gap-1">
						{#each [60, 70, 55, 80, 65, 75, 60] as h, i}
							<div class="flex-1" style="height:{h}%;background:{i === 6 ? '#006f7c' : '#ebe8dd'};border:1px solid #383832"></div>
						{/each}
					</div>
				</div>
				<div class="space-y-2">
					<div class="flex justify-between items-end">
						<span class="font-black uppercase text-[10px] tracking-widest" style="color:#65655e">LLM Token/s</span>
						<span class="text-sm font-mono font-black" style="color:#ff9d00">84.2</span>
					</div>
					<div class="h-12 flex items-end gap-1">
						{#each [30, 40, 35, 50, 45, 55, 40] as h, i}
							<div class="flex-1" style="height:{h}%;background:{i === 6 ? '#ff9d00' : '#ebe8dd'};border:1px solid #383832"></div>
						{/each}
					</div>
				</div>
			</div>
		</div>
	</section>
</div>
