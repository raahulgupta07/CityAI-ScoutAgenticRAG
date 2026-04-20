<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getAuthHeaders } from '$lib/api';

	let loading = $state(true);
	let dd = $state<any>(null);
	let chatHistory = $state<any[]>([]);
	let tenant = $state<any>({});

	const tenantId = $derived((page as any).params?.tenant_id || '');

	onMount(async () => {
		await Promise.all([loadDeepDive(), loadChatHistory()]);
		loading = false;
	});

	async function loadDeepDive() {
		try { dd = await (await fetch(`/api/super/monitoring/tenant/${tenantId}`, { headers: getAuthHeaders() })).json(); } catch {}
	}
	async function loadChatHistory() {
		try { chatHistory = await (await fetch(`/api/super/monitoring/tenant/${tenantId}/chats`, { headers: getAuthHeaders() })).json(); } catch { chatHistory = []; }
	}

	function timeAgo(d: string) {
		if (!d) return '';
		const s = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
		if (s < 60) return `${s}s ago`; if (s < 3600) return `${Math.floor(s/60)}m ago`;
		if (s < 86400) return `${Math.floor(s/3600)}h ago`; return `${Math.floor(s/86400)}d ago`;
	}

	function sopScoreColor(score: number) {
		if (score >= 80) return '#007518';
		if (score >= 60) return '#006f7c';
		if (score >= 40) return '#ff9d00';
		if (score >= 20) return '#f95630';
		return '#be2d06';
	}
</script>

<style>
	@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');

	* {
		border-radius: 0 !important;
		font-family: 'Space Grotesk', sans-serif;
	}

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
		letter-spacing: 0.05em;
	}

	.dark-title-bar {
		background: #383832;
		color: #feffd6;
		padding: 12px 20px;
		font-weight: 900;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.page-bg {
		background: #feffd6;
	}

	.card {
		background: #ffffff;
	}

.btn-cta {
		background: #00fc40;
		color: #383832;
		font-weight: 900;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border: 2px solid #383832;
		box-shadow: 4px 4px 0px 0px #383832;
		transition: transform 0.1s, box-shadow 0.1s;
		cursor: pointer;
	}

	.btn-cta:active {
		transform: translate(2px, 2px);
		box-shadow: 2px 2px 0px 0px #383832;
	}

	.table-header {
		background: #ebe8dd;
		font-weight: 900;
		text-transform: uppercase;
		font-size: 10px;
		letter-spacing: 0.05em;
		color: #383832;
	}

	.table-row-even {
		background: #ffffff;
	}

	.table-row-odd {
		background: #fcf9ef;
	}
</style>

{#if loading}
	<div class="flex items-center justify-center h-64 page-bg">
		<span class="material-symbols-outlined text-3xl animate-pulse" style="color:#65655e">hourglass_empty</span>
	</div>
{:else if dd?.error}
	<div class="p-12 text-center page-bg" style="color:#be2d06; font-weight:900;">{dd.error}</div>
{:else if dd}
<div class="pt-6 space-y-8 page-bg" style="min-height:100vh; padding:24px;">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-4">
			<a href="/monitoring" class="ink-border stamp-shadow p-2 card" style="color:#383832;">
				<span class="material-symbols-outlined">arrow_back</span>
			</a>
			<div>
				<h1 style="font-size:28px; font-weight:900; color:#383832; text-transform:uppercase; letter-spacing:-0.01em;">{dd.tenant?.name || tenantId}</h1>
				<p style="font-size:12px; color:#65655e; text-transform:uppercase; letter-spacing:0.05em;">{dd.tenant?.id} &middot; MODE: {dd.tenant?.document_mode || 'general'}</p>
			</div>
		</div>
		<div class="flex gap-3">
			<a href="/t/{tenantId}/admin" target="_blank" class="btn-cta px-4 py-2 text-xs">OPEN ADMIN PANEL</a>
			<a href="/t/{tenantId}/embed" target="_blank" class="ink-border stamp-shadow card px-4 py-2 text-xs" style="font-weight:900; color:#383832; text-transform:uppercase;">PUBLIC CHAT</a>
		</div>
	</div>

	<!-- Agent Performance Cards -->
	<div class="grid grid-cols-6 gap-4">
		<div class="card ink-border stamp-shadow p-5 text-center">
			<p style="font-size:30px; font-weight:900; color:#006f7c;">{dd.agent_performance?.total_queries || 0}</p>
			<p class="tag-label mt-2" style="display:inline-block;">TOTAL QUERIES</p>
		</div>
		<div class="card ink-border stamp-shadow p-5 text-center">
			<p style="font-size:30px; font-weight:900; color:#383832;">{dd.agent_performance?.avg_response_sec || 0}s</p>
			<p class="tag-label mt-2" style="display:inline-block;">AVG RESPONSE</p>
		</div>
		<div class="card ink-border stamp-shadow p-5 text-center">
			<p style="font-size:30px; font-weight:900; color:#007518;">{dd.agent_performance?.feedback_up || 0}</p>
			<p class="tag-label mt-2" style="display:inline-block;">THUMBS UP</p>
		</div>
		<div class="card ink-border stamp-shadow p-5 text-center">
			<p style="font-size:30px; font-weight:900; color:#be2d06;">{dd.agent_performance?.feedback_down || 0}</p>
			<p class="tag-label mt-2" style="display:inline-block;">THUMBS DOWN</p>
		</div>
		<div class="card ink-border stamp-shadow p-5 text-center">
			<p style="font-size:30px; font-weight:900; color:#006f7c;">{dd.agent_performance?.satisfaction_score || 0}/5</p>
			<p class="tag-label mt-2" style="display:inline-block;">SATISFACTION</p>
		</div>
		<div class="card ink-border stamp-shadow p-5 text-center">
			<p style="font-size:30px; font-weight:900; color:#383832;">{dd.agent_performance?.self_learned_mappings || 0}</p>
			<p class="tag-label mt-2" style="display:inline-block;">SELF-LEARNED</p>
		</div>
	</div>

	<div class="grid grid-cols-12 gap-6">
		<!-- Left: Chat History + Unanswered (8 cols) -->
		<div class="col-span-8 space-y-6">
			<!-- Recent Queries with Feedback -->
			<div class="card ink-border stamp-shadow overflow-hidden">
				<div class="dark-title-bar flex justify-between items-center">
					<h3 style="font-weight:900;">CHAT HISTORY &amp; FEEDBACK</h3>
					<span class="tag-label">{dd.recent_queries?.length || 0} QUERIES</span>
				</div>
				<!-- Table header -->
				<div class="table-header px-6 py-2 flex items-center gap-4">
					<span style="width:24px;">FB</span>
					<span class="flex-1">QUESTION</span>
					<span style="width:50px; text-align:right;">TIME</span>
				</div>
				<div>
					{#each (dd.recent_queries || []) as q, i}
						<div class="px-6 py-3 flex items-center gap-4" class:table-row-even={i % 2 === 0} class:table-row-odd={i % 2 !== 0} style="border-bottom:1px solid #ebe8dd;">
							{#if q.feedback === 'up'}
								<span class="material-symbols-outlined text-lg" style="color:#007518;font-variation-settings:'FILL' 1">thumb_up</span>
							{:else if q.feedback === 'down'}
								<span class="material-symbols-outlined text-lg" style="color:#be2d06;font-variation-settings:'FILL' 1">thumb_down</span>
							{:else}
								<span class="material-symbols-outlined text-lg" style="color:#65655e">radio_button_unchecked</span>
							{/if}
							<span class="text-sm flex-1 truncate" style="color:#383832;">{q.question}</span>
							<span style="font-size:10px; font-weight:900; color:#006f7c; font-family:monospace;">{q.duration}s</span>
						</div>
					{:else}
						<div class="px-6 py-8 text-center" style="color:#65655e; font-weight:900; text-transform:uppercase;">No queries yet</div>
					{/each}
				</div>
			</div>

			<!-- Top Unanswered -->
			{#if dd.top_unanswered?.length}
				<div class="card ink-border stamp-shadow p-6" style="border-left:6px solid #be2d06 !important;">
					<h3 style="font-weight:900; color:#383832; text-transform:uppercase; margin-bottom:12px;" class="flex items-center gap-2">
						<span class="material-symbols-outlined text-lg" style="color:#be2d06">warning</span>
						TOP UNANSWERED QUESTIONS
					</h3>
					<p style="font-size:11px; color:#65655e; margin-bottom:12px; text-transform:uppercase;">These questions had no good answer or received negative feedback. Consider uploading SOPs that cover these topics.</p>
					{#each dd.top_unanswered as q}
						<div class="flex items-center justify-between py-2" style="border-bottom:1px solid #ebe8dd;">
							<span style="font-size:13px; color:#383832;">{q.question}</span>
							<div class="flex gap-4">
								<span class="tag-label">ASKED {q.ask_count}x</span>
								{#if q.down_count > 0}
									<span style="font-size:10px; font-weight:900; color:#be2d06; text-transform:uppercase;">{q.down_count} NEGATIVE</span>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}

			<!-- Conversation Sessions -->
			<div class="card ink-border stamp-shadow overflow-hidden">
				<div class="dark-title-bar">
					<h3 style="font-weight:900;">CONVERSATION SESSIONS</h3>
				</div>
				{#if chatHistory.length > 0}
					<div>
						{#each chatHistory as conv, i}
							<div class="px-6 py-4" class:table-row-even={i % 2 === 0} class:table-row-odd={i % 2 !== 0} style="border-bottom:1px solid #ebe8dd;">
								<div class="flex justify-between items-center mb-2">
									<span style="font-size:13px; font-weight:900; color:#383832;">{conv.title || 'Untitled'}</span>
									<span style="font-size:10px; color:#65655e; text-transform:uppercase; font-weight:700;">{timeAgo(conv.created_at)} &middot; {conv.message_count} MESSAGES</span>
								</div>
								{#if conv.messages}
									{#each conv.messages.slice(0, 4) as msg}
										<div class="flex gap-2 py-1">
											<span style="font-size:10px; font-weight:900; width:40px; flex-shrink:0; color:{msg.role === 'user' ? '#006f7c' : '#007518'}; text-transform:uppercase;">{msg.role === 'user' ? 'USER' : 'BOT'}</span>
											<span style="font-size:12px; color:#65655e;" class="truncate">{msg.content?.slice(0, 120) || ''}</span>
										</div>
									{/each}
									{#if conv.messages.length > 4}
										<p style="font-size:10px; margin-top:4px; color:#65655e; font-weight:700; text-transform:uppercase;">... +{conv.messages.length - 4} more messages</p>
									{/if}
								{/if}
							</div>
						{/each}
					</div>
				{:else}
					<div class="px-6 py-8 text-center" style="color:#65655e; font-weight:900; text-transform:uppercase;">No conversation sessions</div>
				{/if}
			</div>
		</div>

		<!-- Right: Document Health + Cost + Config (4 cols) -->
		<div class="col-span-4 space-y-6">
			<!-- Document Health -->
			<div class="card ink-border stamp-shadow overflow-hidden">
				<div class="dark-title-bar">
					<h3 style="font-weight:900;">DOCUMENT HEALTH</h3>
				</div>
				<div class="p-6">
					<div class="grid grid-cols-2 gap-3">
						<div class="ink-border p-3 text-center" style="background:#fcf9ef;">
							<p style="font-size:20px; font-weight:900; color:#383832;">{dd.document_health?.total_docs || 0}</p>
							<p class="tag-label mt-1" style="display:inline-block;">TOTAL</p>
						</div>
						<div class="ink-border p-3 text-center" style="background:#fcf9ef;">
							<p style="font-size:20px; font-weight:900; color:#006f7c;">{dd.document_health?.avg_sop_score || 0}/100</p>
							<p class="tag-label mt-1" style="display:inline-block;">AVG SCORE</p>
						</div>
						<div class="ink-border p-3 text-center" style="background:#fcf9ef;">
							<p style="font-size:20px; font-weight:900; color:#007518;">{dd.document_health?.excellent || 0}</p>
							<p class="tag-label mt-1" style="display:inline-block;">EXCELLENT</p>
						</div>
						<div class="ink-border p-3 text-center" style="background:#fcf9ef;">
							<p style="font-size:20px; font-weight:900; color:#be2d06;">{dd.document_health?.needs_work || 0}</p>
							<p class="tag-label mt-1" style="display:inline-block;">NEEDS WORK</p>
						</div>
					</div>
					{#if dd.document_health?.stale_docs?.length}
						<div class="mt-4 ink-border p-3" style="background:#fcf9ef; border-left:6px solid #ff9d00 !important;">
							<p style="font-size:10px; font-weight:900; color:#ff9d00; text-transform:uppercase;">STALE SOPs (&gt;6 MONTHS)</p>
							<p style="font-size:12px; color:#65655e; margin-top:4px;">{dd.document_health.stale_docs.join(', ')}</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Cost -->
			<div class="card ink-border stamp-shadow overflow-hidden">
				<div class="dark-title-bar">
					<h3 style="font-weight:900;">COST (30 DAYS)</h3>
				</div>
				<div class="p-6">
					<p style="font-size:30px; font-weight:900; color:#383832;">${(dd.cost?.total_cost_usd || 0).toFixed(3)}</p>
					<p style="font-size:11px; color:#65655e; text-transform:uppercase; font-weight:700; margin-top:4px;">{dd.cost?.total_operations || 0} OPERATIONS</p>
					{#if dd.cost?.by_operation}
						<div class="mt-4 space-y-2">
							{#each dd.cost.by_operation.slice(0, 5) as op}
								<div class="flex justify-between" style="font-size:12px; border-bottom:1px solid #ebe8dd; padding-bottom:4px;">
									<span style="color:#65655e; text-transform:uppercase; font-weight:700;">{op.operation}</span>
									<span style="color:#006f7c; font-weight:900;">${(op.cost || 0).toFixed(3)}</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Agent Config (Full) -->
			<div class="card ink-border stamp-shadow overflow-hidden">
				<div class="dark-title-bar flex justify-between items-center">
					<h3 style="font-weight:900;">AGENT CONFIG</h3>
					<a href="/t/{tenantId}/admin" target="_blank" class="btn-cta px-3 py-1 text-[10px]">EDIT</a>
				</div>
				<div class="p-6 space-y-3" style="font-size:12px;">
					<div class="flex justify-between"><span style="color:#65655e; text-transform:uppercase; font-weight:700;">NAME</span><span style="color:#383832; font-weight:900;">{dd.tenant?.agent_name || '—'}</span></div>
					<div class="flex justify-between"><span style="color:#65655e; text-transform:uppercase; font-weight:700;">ROLE</span><span style="color:#383832; font-weight:900;" class="truncate ml-4" title={dd.tenant?.agent_role}>{dd.tenant?.agent_role || '—'}</span></div>
					<div style="border-top:2px solid #ebe8dd; padding-top:8px; margin-top:4px;">
						<p style="font-size:10px; font-weight:900; color:#65655e; text-transform:uppercase; margin-bottom:6px;">FOCUS AREA</p>
						<p style="font-size:11px; color:#383832; line-height:1.5;">{dd.tenant?.agent_focus || '—'}</p>
					</div>
					<div style="border-top:2px solid #ebe8dd; padding-top:8px;">
						<div class="grid grid-cols-2 gap-2">
							<div><span style="font-size:10px; color:#65655e; font-weight:700; text-transform:uppercase;">TONE</span><br><span style="color:#383832; font-weight:900; text-transform:capitalize;">{dd.tenant?.agent_tone || 'professional'}</span></div>
							<div><span style="font-size:10px; color:#65655e; font-weight:700; text-transform:uppercase;">STYLE</span><br><span style="color:#383832; font-weight:900; text-transform:capitalize;">{dd.tenant?.agent_style || 'step-by-step'}</span></div>
							<div><span style="font-size:10px; color:#65655e; font-weight:700; text-transform:uppercase;">MODE</span><br><span style="color:#383832; font-weight:900;">{dd.tenant?.document_mode || 'general'}</span></div>
							<div><span style="font-size:10px; color:#65655e; font-weight:700; text-transform:uppercase;">TEMPLATE</span><br><span style="color:#383832; font-weight:900;">{dd.tenant?.sop_template || 'auto'}</span></div>
						</div>
					</div>
					<div style="border-top:2px solid #ebe8dd; padding-top:8px;">
						<span style="font-size:10px; color:#65655e; font-weight:700; text-transform:uppercase;">LANGUAGES</span><br>
						<span style="color:#383832; font-weight:900;">{(dd.tenant?.agent_languages || ['English']).join(', ')}</span>
					</div>
					<div style="border-top:2px solid #ebe8dd; padding-top:8px;">
						<span style="font-size:10px; color:#65655e; font-weight:700; text-transform:uppercase;">ADMIN</span><br>
						<span style="color:#383832; font-weight:900;">{dd.tenant?.admin_user || '—'}</span>
						<span style="font-size:10px; margin-left:8px; color:#65655e; font-weight:700; text-transform:uppercase;">CREATED: {dd.tenant?.created_at?.split('T')[0] || '—'}</span>
					</div>
					{#if dd.tenant?.embed_token}
						<div style="border-top:2px solid #ebe8dd; padding-top:8px;">
							<span style="font-size:10px; color:#65655e; font-weight:700; text-transform:uppercase;">PUBLIC CHAT</span><br>
							<a href="/c/{dd.tenant.embed_token}" target="_blank" style="font-size:11px; color:#006f7c; font-weight:900;">/c/{dd.tenant.embed_token.slice(0,12)}...</a>
						</div>
					{/if}
				</div>
			</div>

			<!-- Document List -->
			{#if dd.documents?.length}
				<div class="card ink-border stamp-shadow overflow-hidden">
					<div class="dark-title-bar">
						<h3 style="font-weight:900;">DOCUMENTS ({dd.documents.length})</h3>
					</div>
					<div class="p-4 space-y-2">
						{#each dd.documents as doc}
							<div class="flex items-center justify-between p-3 ink-border" style="background:#fcf9ef;">
								<div>
									<p style="font-size:12px; font-weight:900; color:#383832;">{doc.title || doc.sop_id}</p>
									<p style="font-size:10px; color:#65655e; text-transform:uppercase; font-weight:700;">{doc.department || '—'} &middot; {doc.page_count}P</p>
								</div>
								{#if doc.sop_score > 0}
									<span class="tag-label" style="background:{sopScoreColor(doc.sop_score)};">{doc.sop_score}/100</span>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Quick Stats -->
			<div class="card ink-border stamp-shadow overflow-hidden">
				<div class="dark-title-bar">
					<h3 style="font-weight:900;">PLATFORM STATS</h3>
				</div>
				<div class="p-6 space-y-2" style="font-size:12px;">
					<div class="flex justify-between" style="border-bottom:1px solid #ebe8dd; padding-bottom:4px;"><span style="color:#65655e; text-transform:uppercase; font-weight:700;">DOCUMENTS</span><span style="color:#383832; font-weight:900;">{dd.stats?.total_indexed || 0}</span></div>
					<div class="flex justify-between" style="border-bottom:1px solid #ebe8dd; padding-bottom:4px;"><span style="color:#65655e; text-transform:uppercase; font-weight:700;">PAGES</span><span style="color:#383832; font-weight:900;">{dd.stats?.total_pages || 0}</span></div>
					<div class="flex justify-between" style="border-bottom:1px solid #ebe8dd; padding-bottom:4px;"><span style="color:#65655e; text-transform:uppercase; font-weight:700;">EMBEDDINGS</span><span style="color:#383832; font-weight:900;">{dd.stats?.total_embeddings || 0}</span></div>
					<div class="flex justify-between"><span style="color:#65655e; text-transform:uppercase; font-weight:700;">QUERIES</span><span style="color:#383832; font-weight:900;">{dd.stats?.total_queries || 0}</span></div>
				</div>
			</div>

			<!-- Quick Actions -->
			<div class="card ink-border stamp-shadow overflow-hidden">
				<div class="dark-title-bar">
					<h3 style="font-weight:900;">QUICK ACTIONS</h3>
				</div>
				<div class="p-4 space-y-3">
					<a href="/t/{tenantId}/admin" target="_blank" class="btn-cta flex items-center gap-2 px-4 py-3 text-xs">
						<span class="material-symbols-outlined text-sm">admin_panel_settings</span> OPEN ADMIN PANEL
					</a>
					<a href="/t/{tenantId}/embed" target="_blank" class="ink-border stamp-shadow card flex items-center gap-2 px-4 py-3 text-xs" style="font-weight:900; color:#383832; text-transform:uppercase; display:flex;">
						<span class="material-symbols-outlined text-sm">chat_bubble</span> PUBLIC CHAT
					</a>
					{#if dd.tenant?.embed_token}
						<a href="/c/{dd.tenant.embed_token}" target="_blank" class="ink-border stamp-shadow flex items-center gap-2 px-4 py-3 text-xs" style="background:#fcf9ef; font-weight:900; color:#383832; text-transform:uppercase; display:flex;">
							<span class="material-symbols-outlined text-sm">link</span> SECRET CHAT URL
						</a>
					{/if}
				</div>
			</div>
		</div>
	</div>
</div>
{/if}
