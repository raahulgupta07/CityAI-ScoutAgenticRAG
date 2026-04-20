<script lang="ts">
	import { onMount } from 'svelte';

	let instance = $state<any>(null);
	let loading = $state(true);

	onMount(async () => {
		try {
			const res = await fetch('/api/super/instance');
			if (res.ok) instance = await res.json();
		} catch {}
		loading = false;
	});

	const categoryColors = ['bg-blue-500', 'bg-purple-500', 'bg-orange-500', 'bg-emerald-500', 'bg-sky-500', 'bg-rose-500', 'bg-amber-500', 'bg-indigo-500', 'bg-teal-500', 'bg-pink-500', 'bg-cyan-500', 'bg-lime-500'];
</script>

{#if loading}
	<div class="flex items-center justify-center h-64">
		<span class="material-symbols-outlined text-3xl animate-pulse" style="color:#65655e">hourglass_empty</span>
	</div>
{:else}
<div class="pt-6 section-animate" style="background:#feffd6;min-height:100vh;padding:24px">

	<!-- Page Header -->
	<div class="mb-8">
		<span class="tag-label mb-2">SUPER ADMIN</span>
		<h1 class="font-black text-3xl tracking-tight" style="color:#383832;font-family:'Space Grotesk',sans-serif">Platform Settings</h1>
		<div class="w-24 mt-1" style="border-bottom:4px solid #383832"></div>
	</div>

	<!-- Bento Grid -->
	<div class="grid grid-cols-12 gap-6 items-start">

		<!-- Platform Identity (Large) -->
		<section class="col-span-12 lg:col-span-8 ink-border stamp-shadow bg-white overflow-hidden">
			<div class="dark-title-bar flex items-center gap-2">
				<span class="material-symbols-outlined text-sm" style="color:#feffd6;font-variation-settings:'FILL' 1">hub</span>
				<h3 class="uppercase tracking-widest text-[11px] font-black" style="color:#feffd6;font-family:'Space Grotesk',sans-serif">Platform Identity</h3>
			</div>
			<div class="p-8">
				<div class="grid md:grid-cols-2 gap-12">
					<div class="space-y-1">
						<p class="text-xs font-black uppercase tracking-wider" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Deployment Name</p>
						<p class="text-3xl font-black" style="color:#383832;font-family:'Space Grotesk',sans-serif">Scout Agentic</p>
					</div>
					<div class="space-y-1">
						<p class="text-xs font-black uppercase tracking-wider" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Core Architecture</p>
						<div class="flex items-center gap-3">
							<p class="text-3xl font-black" style="color:#383832;font-family:'Space Grotesk',sans-serif">2.0.0</p>
							<span class="tag-label">MULTI-TENANT</span>
						</div>
					</div>
				</div>
				<div class="mt-12 grid grid-cols-3 gap-4">
					<div class="p-4 ink-border bg-white">
						<p class="text-[10px] uppercase tracking-wider font-black mb-1" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Status</p>
						<div class="flex items-center gap-2">
							<span class="w-2 h-2" style="background:#007518"></span>
							<span class="text-xs font-bold" style="color:#383832">Operational</span>
						</div>
					</div>
					<div class="p-4 ink-border bg-white">
						<p class="text-[10px] uppercase tracking-wider font-black mb-1" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Architecture</p>
						<span class="text-xs font-bold" style="color:#383832">Schema-per-Tenant</span>
					</div>
					<div class="p-4 ink-border bg-white">
						<p class="text-[10px] uppercase tracking-wider font-black mb-1" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Framework</p>
						<span class="text-xs font-bold" style="color:#383832">Agno + PgVector</span>
					</div>
				</div>
			</div>
		</section>

		<!-- System Runtime -->
		<section class="col-span-12 lg:col-span-4 ink-border stamp-shadow bg-white overflow-hidden">
			<div class="dark-title-bar flex items-center justify-between">
				<div class="flex items-center gap-2">
					<span class="material-symbols-outlined text-sm" style="color:#feffd6">terminal</span>
					<h3 class="uppercase tracking-widest text-[11px] font-black" style="color:#feffd6;font-family:'Space Grotesk',sans-serif">System Runtime</h3>
				</div>
				<span class="text-[10px] font-mono" style="color:#feffd6;opacity:0.6">instance.yaml</span>
			</div>
			<div class="p-6">
				<div class="p-4 font-mono text-[11px] leading-relaxed ink-border" style="background:#feffd6;color:#383832">
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">01</span><span><span class="font-bold">platform</span>:</span></div>
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">02</span><span class="pl-4"><span class="font-bold">name</span>: "Scout Agentic"</span></div>
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">03</span><span class="pl-4"><span class="font-bold">version</span>: "2.0.0"</span></div>
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">04</span><span class="pl-4"><span class="font-bold">multi_tenant</span>: true</span></div>
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">05</span><span><span class="font-bold">models</span>:</span></div>
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">06</span><span class="pl-4"><span class="font-bold">chat</span>: gemini-3-flash</span></div>
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">07</span><span class="pl-4"><span class="font-bold">extract</span>: gemini-2.0-flash</span></div>
					<div class="flex gap-4"><span style="color:#65655e" class="select-none">08</span><span class="pl-4"><span class="font-bold">embed</span>: text-embed-3-sm</span></div>
				</div>
				<p class="mt-4 text-[10px] font-bold" style="color:#65655e">Edit <code class="font-mono font-bold" style="color:#383832">instance.yaml</code> and <code class="font-mono font-bold" style="color:#383832">.env</code> to change. Rebuild to apply.</p>
			</div>
		</section>

		<!-- Neural Infrastructure (AI Models) -->
		<section class="col-span-12 ink-border stamp-shadow bg-white overflow-hidden">
			<div class="dark-title-bar flex items-center gap-2">
				<span class="material-symbols-outlined text-sm" style="color:#feffd6;font-variation-settings:'FILL' 1">neurology</span>
				<h3 class="uppercase tracking-widest text-[11px] font-black" style="color:#feffd6;font-family:'Space Grotesk',sans-serif">Neural Infrastructure</h3>
			</div>
			<div class="p-8">
				<div class="grid md:grid-cols-3 gap-6">
					<!-- Chat + Vision -->
					<div class="p-6 ink-border bg-white hover:-translate-y-1 transition-transform duration-300">
						<div class="flex items-start justify-between mb-4">
							<span class="material-symbols-outlined" style="color:#383832">chat_bubble</span>
							<span class="tag-label">PRIMARY</span>
						</div>
						<h4 class="text-xs font-black uppercase tracking-tight mb-2" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Chat + Vision</h4>
						<p class="text-lg font-black truncate" style="color:#383832;font-family:'Space Grotesk',sans-serif">gemini-3-flash-preview</p>
						<div class="mt-4 pt-4 flex items-center justify-between text-[10px]" style="border-top:2px solid #383832">
							<span class="font-bold" style="color:#65655e">Latency: <span style="color:#383832">120ms</span></span>
							<span class="font-black" style="color:#007518">ACTIVE</span>
						</div>
					</div>
					<!-- Categorize + Extract -->
					<div class="p-6 ink-border bg-white hover:-translate-y-1 transition-transform duration-300">
						<div class="flex items-start justify-between mb-4">
							<span class="material-symbols-outlined" style="color:#383832">database</span>
							<span class="tag-label">UTILITY</span>
						</div>
						<h4 class="text-xs font-black uppercase tracking-tight mb-2" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Categorize + Extract</h4>
						<p class="text-lg font-black truncate" style="color:#383832;font-family:'Space Grotesk',sans-serif">gemini-2.0-flash-001</p>
						<div class="mt-4 pt-4 flex items-center justify-between text-[10px]" style="border-top:2px solid #383832">
							<span class="font-bold" style="color:#65655e">Latency: <span style="color:#383832">85ms</span></span>
							<span class="font-black" style="color:#007518">ACTIVE</span>
						</div>
					</div>
					<!-- Embeddings -->
					<div class="p-6 ink-border bg-white hover:-translate-y-1 transition-transform duration-300">
						<div class="flex items-start justify-between mb-4">
							<span class="material-symbols-outlined" style="color:#383832">data_array</span>
							<span class="tag-label">VECTOR</span>
						</div>
						<h4 class="text-xs font-black uppercase tracking-tight mb-2" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Embeddings</h4>
						<p class="text-lg font-black truncate" style="color:#383832;font-family:'Space Grotesk',sans-serif">text-embedding-3-small</p>
						<div class="mt-4 pt-4 flex items-center justify-between text-[10px]" style="border-top:2px solid #383832">
							<span class="font-bold" style="color:#65655e">Dimensions: <span style="color:#383832">1536</span></span>
							<span class="font-black" style="color:#007518">ACTIVE</span>
						</div>
					</div>
				</div>
			</div>
		</section>

		<!-- Default Taxonomy (Categories) -->
		{#if instance?.categories}
		<section class="col-span-12 lg:col-span-6 ink-border stamp-shadow bg-white overflow-hidden">
			<div class="dark-title-bar flex items-center justify-between">
				<div class="flex items-center gap-2">
					<span class="material-symbols-outlined text-sm" style="color:#feffd6;font-variation-settings:'FILL' 1">label_important</span>
					<h3 class="uppercase tracking-widest text-[11px] font-black" style="color:#feffd6;font-family:'Space Grotesk',sans-serif">Default Taxonomy</h3>
				</div>
				<span class="text-[10px] font-mono" style="color:#feffd6;opacity:0.6">instance.yaml</span>
			</div>
			<div class="p-8">
				<div class="flex flex-wrap gap-3">
					{#each instance.categories as cat, i}
						<span class="px-3 py-1.5 text-xs font-bold flex items-center gap-2 ink-border" style="background:#feffd6;color:#383832">
							<span class="w-2 h-2 {categoryColors[i % categoryColors.length]}"></span>
							{cat.split('/').pop()}
						</span>
					{/each}
				</div>
			</div>
		</section>
		{/if}

		<!-- System Integrity -->
		<section class="col-span-12 lg:col-span-6 ink-border stamp-shadow bg-white overflow-hidden">
			<div class="dark-title-bar flex items-center gap-2">
				<span class="material-symbols-outlined text-sm" style="color:#feffd6;font-variation-settings:'FILL' 1">shield_with_heart</span>
				<h3 class="uppercase tracking-widest text-[11px] font-black" style="color:#feffd6;font-family:'Space Grotesk',sans-serif">System Integrity</h3>
			</div>
			<div class="p-8 flex items-center gap-8">
				<div class="w-32 h-32 flex-shrink-0 flex items-center justify-center relative ink-border" style="background:#feffd6">
					<span class="material-symbols-outlined text-4xl" style="color:#383832;font-variation-settings:'FILL' 1">shield_with_heart</span>
					<svg class="absolute inset-0 w-full h-full -rotate-90">
						<circle cx="64" cy="64" r="60" fill="none" stroke="#383832" stroke-width="2" opacity="0.2"></circle>
						<circle cx="64" cy="64" r="60" fill="none" stroke="#007518" stroke-width="4" stroke-dasharray="377" stroke-dashoffset="40"></circle>
					</svg>
				</div>
				<div class="space-y-4">
					<div>
						<h4 class="text-lg font-black" style="color:#383832;font-family:'Space Grotesk',sans-serif">System Integrity High</h4>
						<p class="text-sm leading-relaxed" style="color:#65655e">Agentic workflows operating within designated safety parameters. Each tenant has full data isolation via PostgreSQL schemas.</p>
					</div>
					<div class="flex gap-4">
						<div class="text-center p-3 ink-border" style="background:#feffd6">
							<p class="text-xl font-black" style="color:#383832;font-family:'Space Grotesk',sans-serif">99.9%</p>
							<p class="text-[10px] uppercase font-black" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Uptime</p>
						</div>
						<div class="w-0.5 self-stretch" style="background:#383832"></div>
						<div class="text-center p-3 ink-border" style="background:#feffd6">
							<p class="text-xl font-black" style="color:#383832;font-family:'Space Grotesk',sans-serif">0</p>
							<p class="text-[10px] uppercase font-black" style="color:#65655e;font-family:'Space Grotesk',sans-serif">Violations</p>
						</div>
					</div>
				</div>
			</div>
		</section>
	</div>
</div>
{/if}
