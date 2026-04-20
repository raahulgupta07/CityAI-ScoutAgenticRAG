<script lang="ts">
	import { onMount } from 'svelte';
	import { getAuthHeaders } from '$lib/api';

	let loading = $state(true);
	let platform = $state<any>({});
	let tenants = $state<any[]>([]);
	let health = $state<any>({});

	// Create tenant
	let showCreate = $state(false);
	let newName = $state('');
	let newId = $state('');
	let newUser = $state('admin');
	let newPass = $state('');
	let newAgentName = $state('');
	let newAgentRole = $state('document intelligence assistant');
	let newFocus = $state('');
	let newTone = $state('professional');
	let newStyle = $state('step-by-step');
	let newDocMode = $state('general');
	let newSopTemplate = $state('auto');
	let newLangs = $state('English');
	let newSystemPrompt = $state('');
	let createMsg = $state('');
	let createdTenant = $state<any>(null);

	// Edit tenant
	let editTenant = $state<any>(null);
	let editPass = $state('');
	let editMsg = $state('');
	let showEditPass = $state(false);

	onMount(async () => {
		await Promise.all([loadPlatform(), loadTenants(), loadHealth()]);
		loading = false;
	});

	async function loadPlatform() {
		try { platform = await (await fetch('/api/super/stats', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadTenants() {
		try { tenants = await (await fetch('/api/super/tenants', { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadHealth() {
		try { health = await (await fetch('/api/super/health', { headers: getAuthHeaders() })).json(); } catch {}
	}

	function generateTenantId() {
		return 'T' + Date.now().toString().slice(-8) + Math.floor(Math.random() * 100).toString().padStart(2, '0');
	}

	function openCreateForm() {
		showCreate = !showCreate;
		createdTenant = null;
		createMsg = '';
		if (showCreate && !newId) newId = generateTenantId();
	}

	let showNewPass = $state(false);

	function slugify(s: string) { return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40); }

	async function createTenant() {
		createMsg = ''; createdTenant = null;
		if (!newName) { createMsg = 'Name is required'; return; }
		if (!newPass) { createMsg = 'Password is required'; return; }
		const body = { id: newId || slugify(newName), name: newName, admin_user: newUser, admin_pass: newPass,
			agent_name: newAgentName || `${newName} Agent`, agent_role: newAgentRole, agent_focus: newFocus,
			agent_tone: newTone, agent_style: newStyle, document_mode: newDocMode,
			sop_template: newSopTemplate, agent_languages: newLangs.split(',').map(s => s.trim()).filter(Boolean),
			agent_system_prompt: newSystemPrompt };
		try {
			const res = await fetch('/api/super/tenants', { method: 'POST', headers: { 'Content-Type': 'application/json', ...getAuthHeaders() }, body: JSON.stringify(body) });
			const data = await res.json();
			if (data.error) { createMsg = data.error; return; }
			createdTenant = { ...data, name: newName, admin_user: newUser };
			newName = ''; newId = generateTenantId(); newUser = 'admin'; newPass = ''; newAgentName = ''; newFocus = ''; showNewPass = false;
			await loadTenants(); await loadPlatform();
		} catch (e: any) { createMsg = e.message; }
	}

	async function deleteTenant(id: string, name: string) {
		if (!confirm(`Delete "${name}" (${id})?\n\nThis permanently removes ALL documents, embeddings, conversations, and agent data.`)) return;
		await fetch(`/api/super/tenants/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
		await loadTenants(); await loadPlatform();
	}

	async function toggleEmbed(id: string, currentState: boolean | undefined) {
		const newState = currentState === false;
		await fetch(`/api/super/tenants/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...getAuthHeaders() }, body: JSON.stringify({ embed_enabled: newState }) });
		await loadTenants();
	}

	async function toggleActive(t: any) {
		await fetch(`/api/super/tenants/${t.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...getAuthHeaders() }, body: JSON.stringify({ is_active: !t.is_active }) });
		await loadTenants();
	}

	async function saveEdit() {
		editMsg = '';
		const body: any = { name: editTenant.name, agent_name: editTenant.agent_name, agent_role: editTenant.agent_role,
			agent_focus: editTenant.agent_focus, admin_user: editTenant.admin_user };
		if (editPass) body.admin_pass = editPass;
		try {
			const res = await fetch(`/api/super/tenants/${editTenant.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...getAuthHeaders() }, body: JSON.stringify(body) });
			const data = await res.json();
			editMsg = data.status === 'updated' ? 'Saved!' : (data.error || 'Error');
			await loadTenants();
			setTimeout(() => { editMsg = ''; editTenant = null; }, 2000);
		} catch (e: any) { editMsg = e.message; }
	}

	async function regenerateToken(id: string) {
		if (!confirm('Regenerate public chat URL? Old URL will stop working.')) return;
		await fetch(`/api/super/tenants/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...getAuthHeaders() }, body: JSON.stringify({ regenerate_token: true }) });
		await loadTenants();
	}

	function timeAgo(ts: string): string {
		if (!ts) return 'Never';
		const diff = (Date.now() - new Date(ts).getTime()) / 1000;
		if (diff < 60) return 'just now';
		if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
		if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
		return `${Math.floor(diff / 86400)}d ago`;
	}
</script>

<div class="pt-6 space-y-6 section-animate">

	<!-- ═══ Health Status Bar ═══ -->
	<div class="flex flex-wrap gap-3">
		{#each Object.entries(health) as [name, check]}
			{@const c = check as any}
			{@const label = name === 'database' ? 'DATABASE' : name === 'pgvector' ? 'PGVECTOR' : name === 'llm' ? 'LLM' : 'DISK'}
			{@const ok = c.status === 'ok'}
			{@const warn = c.status === 'warning'}
			<div class="flex items-center gap-2 px-3 py-2 bg-white" style="border:2px solid #383832;box-shadow:3px 3px 0px 0px #383832">
				<span class="w-2 h-2 inline-block" style="background:{ok ? '#007518' : warn ? '#ff9d00' : '#be2d06'}"></span>
				<span class="text-[10px] font-black uppercase tracking-wider" style="color:#383832">{label}</span>
				<span class="text-[10px] font-black uppercase ml-1" style="color:{ok ? '#007518' : warn ? '#ff9d00' : '#be2d06'}">{ok ? 'OK' : warn ? 'WARN' : 'ERR'}</span>
			</div>
		{/each}
	</div>

	<!-- ═══ KPI Cards ═══ -->
	<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
		<!-- Tenants -->
		<div class="p-4 bg-white ink-border stamp-shadow">
			<div class="flex justify-between items-start mb-2">
				<span class="tag-label">TOTAL TENANTS</span>
				<span class="material-symbols-outlined text-lg" style="color:#007518">groups</span>
			</div>
			<div class="text-4xl font-black tracking-tighter" style="color:#383832">{platform.total_tenants || 0}</div>
			<div class="mt-3 h-2" style="background:#ebe8dd;border:1px solid #383832">
				<div class="h-full" style="background:#007518;width:{Math.min((platform.total_tenants || 0) * 10, 100)}%"></div>
			</div>
			<div class="mt-2 text-[10px] font-bold uppercase" style="color:#383832;opacity:0.6">{platform.active_tenants || 0} active</div>
		</div>

		<!-- Documents -->
		<div class="p-4 bg-white ink-border stamp-shadow">
			<div class="flex justify-between items-start mb-2">
				<span class="tag-label">DOCUMENTS</span>
				<span class="material-symbols-outlined text-lg" style="color:#006f7c">description</span>
			</div>
			<div class="text-4xl font-black tracking-tighter" style="color:#383832">{platform.total_documents || 0}</div>
			<div class="mt-2 text-[10px] font-bold uppercase" style="color:#383832;opacity:0.6">{platform.total_embeddings || 0} embeddings</div>
		</div>

		<!-- Queries 24h -->
		<div class="p-4 bg-white ink-border stamp-shadow">
			<div class="flex justify-between items-start mb-2">
				<span class="tag-label">QUERIES 24H</span>
				<span class="material-symbols-outlined text-lg" style="color:#ff9d00">bolt</span>
			</div>
			<div class="text-4xl font-black tracking-tighter" style="color:#383832">{platform.total_queries_24h || 0}</div>
			<div class="mt-2 text-[10px] font-bold uppercase" style="color:#383832;opacity:0.6">{platform.total_queries || 0} all time</div>
		</div>

		<!-- System -->
		<div class="p-4 bg-white ink-border stamp-shadow">
			<div class="flex justify-between items-start mb-2">
				<span class="tag-label">SYSTEM</span>
				<span class="material-symbols-outlined text-lg" style="color:#9d4867">timer</span>
			</div>
			<div class="text-2xl font-black tracking-tighter" style="color:#383832">{platform.uptime || '--'}</div>
			<div class="mt-2 text-[10px] font-bold uppercase" style="color:#383832;opacity:0.6">DB: {platform.db_size_mb || 0}MB / Disk: {platform.storage_mb || 0}MB</div>
		</div>
	</div>

	<!-- ═══ Tenant Management ═══ -->
	<div class="border-2 stamp-shadow" style="border-color:#383832;background:white">
		<!-- Title bar -->
		<div class="dark-title-bar flex items-center justify-between">
			<span class="flex items-center gap-2">
				<span class="material-symbols-outlined text-sm" style="color:#ff9d00">hub</span>
				TENANT_REGISTRY
			</span>
			<button onclick={openCreateForm}
				class="text-[10px] font-black uppercase tracking-wider px-4 py-1.5 cursor-pointer active:translate-x-[2px] active:translate-y-[2px] transition-transform"
				style={showCreate
					? 'background:#383832;color:#feffd6;border:1px solid #65655e'
					: 'background:#00fc40;color:#383832;border:2px solid #383832;box-shadow:2px 2px 0px 0px rgba(56,56,50,0.5)'}>
				{showCreate ? 'CANCEL' : '+ NEW_TENANT'}
			</button>
		</div>

		<!-- ═══ Create Form ═══ -->
		{#if showCreate}
			<div class="p-5" style="background:#f6f4e9;border-bottom:2px solid #383832">
				{#if createdTenant}
					<!-- Success -->
					<div class="p-4 bg-white" style="border:2px solid #007518">
						<div class="flex items-center gap-2 mb-3">
							<span class="material-symbols-outlined" style="color:#007518">check_circle</span>
							<span class="text-sm font-black uppercase" style="color:#007518">Tenant "{createdTenant.name}" created!</span>
						</div>
						<div class="grid grid-cols-2 gap-3">
							<div>
								<span class="tag-label mb-1">ADMIN PANEL</span>
								<div class="flex items-center gap-2 mt-1">
									<code class="text-xs font-mono px-2 py-1 flex-1 truncate" style="background:#ebe8dd;border:1px solid #383832">{location.origin}{createdTenant.admin_url}</code>
									<button onclick={() => navigator.clipboard.writeText(location.origin + createdTenant.admin_url)} class="text-[10px] font-black cursor-pointer" style="color:#007518">COPY</button>
								</div>
							</div>
							<div>
								<span class="tag-label mb-1">PUBLIC CHAT</span>
								<div class="flex items-center gap-2 mt-1">
									<code class="text-xs font-mono px-2 py-1 flex-1 truncate" style="background:#ebe8dd;border:1px solid #383832">{location.origin}/c/{createdTenant.embed_token}</code>
									<button onclick={() => navigator.clipboard.writeText(location.origin + '/c/' + createdTenant.embed_token)} class="text-[10px] font-black cursor-pointer" style="color:#007518">COPY</button>
								</div>
							</div>
							<div>
								<span class="tag-label mb-1">ADMIN LOGIN</span>
								<code class="text-xs font-mono px-2 py-1 block mt-1" style="background:#ebe8dd;border:1px solid #383832">{createdTenant.admin_user}</code>
							</div>
							<div>
								<span class="tag-label mb-1">WIDGET CODE</span>
								<code class="text-[10px] font-mono px-2 py-1 block mt-1 truncate" style="background:#ebe8dd;border:1px solid #383832">&lt;script src="/widget.js" data-token="{createdTenant.embed_token}"&gt;</code>
							</div>
						</div>
						<button onclick={() => { showCreate = false; createdTenant = null; }} class="mt-3 text-[10px] font-black uppercase cursor-pointer" style="color:#007518">DONE</button>
					</div>
				{:else}
					{#if createMsg}
						<div class="mb-3 px-3 py-2 text-xs font-bold uppercase" style="background:#be2d06;color:white;border:2px solid #383832">{createMsg}</div>
					{/if}
					<div class="grid grid-cols-2 gap-4">
						<div>
							<div class="tag-label mb-1">TENANT ID <span class="font-normal" style="color:#9d9d91">(AUTO)</span></div>
							<input bind:value={newId} readonly class="w-full px-3 py-2.5 text-sm font-mono cursor-default" style="background:#ebe8dd;border:2px solid #383832;color:#65655e" />
						</div>
						<div>
							<div class="tag-label mb-1">COMPANY NAME *</div>
							<input bind:value={newName} placeholder="e.g. HR Department" class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
						</div>
						<div>
							<div class="tag-label mb-1">ADMIN USERNAME</div>
							<input bind:value={newUser} placeholder="admin" class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
						</div>
						<div>
							<div class="tag-label mb-1">ADMIN PASSWORD *</div>
							<div class="relative">
								<input bind:value={newPass} type={showNewPass ? 'text' : 'password'} placeholder="Enter password" class="w-full px-3 py-2.5 pr-10 text-sm font-bold font-mono" style="background:white;border:2px solid #383832;color:#383832" />
								<button type="button" onclick={() => showNewPass = !showNewPass} class="absolute right-3 top-1/2 -translate-y-1/2 cursor-pointer" style="color:#65655e">
									<span class="material-symbols-outlined text-[16px]">{showNewPass ? 'visibility_off' : 'visibility'}</span>
								</button>
							</div>
						</div>
						<div>
							<div class="tag-label mb-1">AGENT NAME</div>
							<input bind:value={newAgentName} placeholder="Auto from company name" class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
						</div>
						<div>
							<div class="tag-label mb-1">AGENT ROLE</div>
							<select bind:value={newAgentRole} class="w-full px-3 py-2.5 text-sm font-bold uppercase" style="background:white;border:2px solid #383832;color:#383832">
								<option value="document intelligence assistant">General</option>
								<option value="IT service management specialist">IT / ITSM</option>
								<option value="HR policy and compliance expert">HR</option>
								<option value="safety and compliance officer">Safety / EHS</option>
								<option value="legal and regulatory advisor">Legal</option>
								<option value="finance and accounting specialist">Finance</option>
								<option value="operations and manufacturing expert">Operations</option>
								<option value="customer service specialist">Customer Service</option>
							</select>
						</div>
						<div style="grid-column:span 2">
							<div class="tag-label mb-1">AGENT FOCUS *</div>
							<input bind:value={newFocus} placeholder="e.g. policies, guides, procedures, incident management" class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
						</div>
						<div>
							<div class="tag-label mb-1">TONE</div>
							<select bind:value={newTone} class="w-full px-3 py-2.5 text-sm font-bold uppercase" style="background:white;border:2px solid #383832;color:#383832">
								<option value="professional">Professional</option>
								<option value="friendly">Friendly</option>
								<option value="technical">Technical</option>
								<option value="executive">Executive</option>
								<option value="casual">Casual</option>
							</select>
						</div>
						<div>
							<div class="tag-label mb-1">RESPONSE STYLE</div>
							<select bind:value={newStyle} class="w-full px-3 py-2.5 text-sm font-bold uppercase" style="background:white;border:2px solid #383832;color:#383832">
								<option value="step-by-step">Step-by-Step</option>
								<option value="narrative">Narrative</option>
								<option value="concise">Concise</option>
								<option value="detailed">Detailed</option>
							</select>
						</div>
						<div>
							<div class="tag-label mb-1">DOCUMENT MODE</div>
							<select bind:value={newDocMode} class="w-full px-3 py-2.5 text-sm font-bold uppercase" style="background:white;border:2px solid #383832;color:#383832">
								<option value="general">General</option>
								<option value="sop">Document Standardize</option>
							</select>
						</div>
						<div>
							<div class="tag-label mb-1">STANDARDIZE TEMPLATE</div>
							<select bind:value={newSopTemplate} class="w-full px-3 py-2.5 text-sm font-bold uppercase" style="background:white;border:2px solid #383832;color:#383832">
								<option value="auto">Auto-detect</option>
								<option value="itsm">ITSM</option>
								<option value="hr">HR</option>
								<option value="safety">Safety / EHS</option>
								<option value="manufacturing">Manufacturing</option>
								<option value="general">General</option>
							</select>
						</div>
						<div>
							<div class="tag-label mb-1">LANGUAGES</div>
							<input bind:value={newLangs} placeholder="English, Burmese" class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
						</div>
						<div>
							<div class="tag-label mb-1">SYSTEM PROMPT <span class="font-normal" style="color:#9d9d91">(OPTIONAL)</span></div>
							<input bind:value={newSystemPrompt} placeholder="Custom agent instructions" class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
						</div>
					</div>
					<button onclick={createTenant}
						class="mt-4 px-6 py-2.5 font-black text-sm uppercase tracking-wider cursor-pointer active:translate-x-[2px] active:translate-y-[2px] transition-transform"
						style="background:#00fc40;color:#383832;border:2px solid #383832;box-shadow:4px 4px 0px 0px #383832">
						CREATE_TENANT
					</button>
				{/if}
			</div>
		{/if}

		<!-- ═══ Tenant Table ═══ -->
		{#if loading}
			<div class="py-12 text-center">
				<span class="material-symbols-outlined text-2xl animate-pulse" style="color:#383832">hourglass_empty</span>
				<p class="text-[10px] font-black uppercase tracking-widest mt-2" style="color:#65655e">LOADING_TENANTS</p>
			</div>
		{:else if tenants.length === 0}
			<!-- Empty state -->
			<div class="py-16 text-center" style="background:#f6f4e9">
				<span class="material-symbols-outlined text-5xl" style="color:#ebe8dd">domain_disabled</span>
				<h2 class="text-3xl font-black uppercase tracking-tighter mt-4" style="color:#383832">NO TENANTS YET</h2>
				<p class="text-sm font-bold mt-2 max-w-md mx-auto" style="color:#65655e">Deploy a new tenant to begin multi-entity management and resource allocation.</p>
				<button onclick={() => { showCreate = true; createdTenant = null; if (!newId) newId = generateTenantId(); }}
					class="mt-6 px-8 py-3 font-black text-sm uppercase tracking-wider cursor-pointer active:translate-x-[2px] active:translate-y-[2px] transition-transform inline-flex items-center gap-2"
					style="background:#00fc40;color:#383832;border:2px solid #383832;box-shadow:4px 4px 0px 0px #383832">
					<span class="material-symbols-outlined text-sm">add</span>
					NEW_TENANT
				</button>
			</div>
		{:else}
			<div class="overflow-x-auto" style="background:white;max-height:500px;overflow-y:auto">
				<table class="w-full" style="border-collapse:collapse;font-size:0.75rem">
					<thead style="background:#ebe8dd;position:sticky;top:0;z-index:1">
						<tr>
							<th class="text-left px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">STATUS</th>
							<th class="text-left px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">TENANT</th>
							<th class="text-left px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">AGENT</th>
							<th class="text-center px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">DOCS</th>
							<th class="text-center px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">24H</th>
							<th class="text-center px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">TOTAL</th>
							<th class="text-center px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">FEEDBACK</th>
							<th class="text-center px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">AVG</th>
							<th class="text-left px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">LAST ACTIVE</th>
							<th class="text-right px-4 py-2 text-[10px] font-black uppercase" style="border-bottom:2px solid #383832">ACTIONS</th>
						</tr>
					</thead>
					<tbody>
						{#each tenants as t, i}
							{@const s = t.stats || {}}
							{@const fbTotal = (s.feedback_up || 0) + (s.feedback_down || 0)}
							{@const fbPct = fbTotal > 0 ? Math.round((s.feedback_up || 0) / fbTotal * 100) : -1}
							<tr style="border-bottom:1px solid rgba(56,56,50,0.15);background:{i % 2 === 0 ? 'white' : '#fcf9ef'}">
								<td class="px-4 py-2.5">
									<button onclick={() => toggleActive(t)} class="cursor-pointer" title={t.is_active ? 'Active' : 'Inactive'}>
										<span class="w-2.5 h-2.5 inline-block" style="background:{t.is_active ? '#007518' : '#9d9d91'}"></span>
									</button>
								</td>
								<td class="px-4 py-2.5">
									<div class="text-sm font-bold" style="color:#383832">
										{t.name}
										{#if t.embed_enabled === false}
											<span class="ml-1 px-1.5 py-0.5 text-[8px] font-black uppercase" style="background:#ff9d00;color:white">EMBED OFF</span>
										{/if}
									</div>
									<div class="text-[10px] font-mono" style="color:#65655e">{t.id} / {t.admin_user}</div>
								</td>
								<td class="px-4 py-2.5">
									<div class="text-xs font-bold" style="color:#383832">{t.agent_name || '--'}</div>
									<div class="text-[10px] truncate max-w-[150px]" style="color:#65655e">{t.agent_focus || '--'}</div>
								</td>
								<td class="px-4 py-2.5 text-center">
									<span class="text-sm font-black" style="color:#383832">{s.documents || 0}</span>
									<span class="text-[10px] block" style="color:#65655e">{s.pages || 0}p</span>
								</td>
								<td class="px-4 py-2.5 text-center">
									<span class="text-sm font-black" style="color:{(s.queries_24h || 0) > 0 ? '#007518' : '#65655e'}">{s.queries_24h || 0}</span>
								</td>
								<td class="px-4 py-2.5 text-center">
									<span class="text-xs font-bold" style="color:#383832">{s.queries_total || 0}</span>
								</td>
								<td class="px-4 py-2.5 text-center">
									{#if fbPct >= 0}
										<span class="px-1.5 py-0.5 text-[9px] font-black uppercase" style="background:{fbPct >= 80 ? '#007518' : fbPct >= 50 ? '#ff9d00' : '#be2d06'};color:white">{fbPct}%</span>
									{:else}
										<span class="text-xs" style="color:#65655e">--</span>
									{/if}
								</td>
								<td class="px-4 py-2.5 text-center">
									<span class="text-xs font-bold" style="color:#383832">{s.avg_duration ? s.avg_duration + 's' : '--'}</span>
								</td>
								<td class="px-4 py-2.5">
									<span class="text-[10px] font-bold" style="color:#65655e">{timeAgo(s.last_query)}</span>
								</td>
								<td class="px-4 py-2.5 text-right">
									<div class="flex items-center justify-end gap-1">
										<a href="/t/{t.id}/admin" target="_blank"
											class="text-[10px] font-black uppercase px-2 py-1 cursor-pointer" style="color:#006f7c;border:1px solid #006f7c">Admin</a>
										{#if t.embed_token}
											<a href="/c/{t.embed_token}" target="_blank"
												class="text-[10px] font-black uppercase px-2 py-1 cursor-pointer" style="color:#007518;border:1px solid #007518">Chat</a>
										{/if}
										<button onclick={() => { editTenant = {...t}; editPass = ''; editMsg = ''; }}
											class="text-[10px] font-black uppercase px-2 py-1 cursor-pointer" style="color:#383832;border:1px solid #383832">Edit</button>
										<button onclick={() => deleteTenant(t.id, t.name)}
											class="text-[10px] font-black uppercase px-2 py-1 cursor-pointer" style="color:#be2d06;border:1px solid #be2d06">Delete</button>
									</div>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>

	<!-- ═══ Edit Modal ═══ -->
	{#if editTenant}
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="fixed inset-0 z-50 flex items-center justify-center" style="background:rgba(56,56,50,0.5)" onclick={(e) => { if (e.target === e.currentTarget) editTenant = null; }}>
			<div class="w-[520px] max-h-[90vh] overflow-y-auto bg-white ink-border stamp-shadow">
				<!-- Header -->
				<div class="dark-title-bar flex items-center justify-between">
					<span>EDIT: {editTenant.name}</span>
					<button onclick={() => editTenant = null} class="cursor-pointer" style="color:#feffd6">
						<span class="material-symbols-outlined text-[20px]">close</span>
					</button>
				</div>
				<!-- Form -->
				<div class="p-5 space-y-4" style="background:#f6f4e9">
					<div>
						<div class="tag-label mb-1">COMPANY NAME</div>
						<input bind:value={editTenant.name} class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
					</div>
					<div class="grid grid-cols-2 gap-4">
						<div>
							<div class="tag-label mb-1">ADMIN USERNAME</div>
							<input bind:value={editTenant.admin_user} class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
						</div>
						<div>
							<div class="tag-label mb-1">RESET PASSWORD</div>
							<div class="relative">
								<input bind:value={editPass} type={showEditPass ? 'text' : 'password'} placeholder="Leave empty to keep" class="w-full px-3 py-2.5 pr-10 text-sm font-bold font-mono" style="background:white;border:2px solid #383832;color:#383832" />
								<button type="button" onclick={() => showEditPass = !showEditPass} class="absolute right-3 top-1/2 -translate-y-1/2 cursor-pointer" style="color:#65655e">
									<span class="material-symbols-outlined text-[16px]">{showEditPass ? 'visibility_off' : 'visibility'}</span>
								</button>
							</div>
						</div>
					</div>
					<div>
						<div class="tag-label mb-1">AGENT NAME</div>
						<input bind:value={editTenant.agent_name} class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
					</div>
					<div>
						<div class="tag-label mb-1">AGENT FOCUS</div>
						<input bind:value={editTenant.agent_focus} class="w-full px-3 py-2.5 text-sm font-bold" style="background:white;border:2px solid #383832;color:#383832" />
					</div>
					<!-- URLs -->
					<div class="pt-3" style="border-top:2px solid #383832">
						<div class="tag-label mb-2">URLS</div>
						<div class="space-y-2">
							<div class="flex items-center gap-2">
								<span class="text-[10px] font-black uppercase w-14" style="color:#65655e">Admin:</span>
								<code class="text-[10px] font-mono px-2 py-1 flex-1 truncate" style="background:#ebe8dd;border:1px solid #383832">{location.origin}/t/{editTenant.id}/admin</code>
								<button onclick={() => navigator.clipboard.writeText(location.origin + '/t/' + editTenant.id + '/admin')} class="text-[10px] font-black cursor-pointer" style="color:#007518">COPY</button>
							</div>
							{#if editTenant.embed_token}
								<div class="flex items-center gap-2">
									<span class="text-[10px] font-black uppercase w-14" style="color:#65655e">Chat:</span>
									<code class="text-[10px] font-mono px-2 py-1 flex-1 truncate" style="background:#ebe8dd;border:1px solid #383832">{location.origin}/c/{editTenant.embed_token}</code>
									<button onclick={() => navigator.clipboard.writeText(location.origin + '/c/' + editTenant.embed_token)} class="text-[10px] font-black cursor-pointer" style="color:#007518">COPY</button>
									<button onclick={() => regenerateToken(editTenant.id)} class="text-[10px] font-black cursor-pointer" style="color:#ff9d00">REGEN</button>
								</div>
							{/if}
						</div>
					</div>
				</div>
				<!-- Footer -->
				<div class="flex items-center justify-between px-5 py-3" style="background:#ebe8dd;border-top:2px solid #383832">
					<span class="text-xs font-black uppercase" style="color:{editMsg === 'Saved!' ? '#007518' : '#be2d06'}">{editMsg}</span>
					<div class="flex gap-2">
						<button onclick={() => editTenant = null}
							class="px-4 py-2 text-xs font-black uppercase cursor-pointer" style="background:#383832;color:#feffd6;border:2px solid #383832">CANCEL</button>
						<button onclick={saveEdit}
							class="px-4 py-2 text-xs font-black uppercase cursor-pointer active:translate-x-[2px] active:translate-y-[2px] transition-transform"
							style="background:#00fc40;color:#383832;border:2px solid #383832;box-shadow:3px 3px 0px 0px #383832">SAVE_CHANGES</button>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>
