<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { onMount } from 'svelte';

	let { children } = $props();

	let instance = $state<any>({
		app: { name: 'Document Agent', tagline: 'Intelligent Curator', icon: 'hub' },
	});

	let authenticated = $state(false);
	let authRequired = $state(false);
	let loginUser = $state('');
	let loginPass = $state('');
	let authError = $state('');
	let checkingAuth = $state(true);
	let adminUser = $state('');
	let showPass = $state(false);

	onMount(async () => {
		try {
			const res = await fetch('/api/super/instance');
			if (res.ok) instance = await res.json();
		} catch {}

		const savedToken = localStorage.getItem('admin_token') || '';
		try {
			const checkRes = await fetch('/api/auth/check', {
				headers: savedToken ? { 'Authorization': `Bearer ${savedToken}` } : {},
			});
			const data = await checkRes.json();
			authRequired = data.auth_required;
			authenticated = data.authenticated;
			if (authenticated) adminUser = localStorage.getItem('admin_user') || 'Admin';
		} catch {
			authenticated = true;
		}
		checkingAuth = false;
	});

	async function login() {
		authError = '';
		try {
			const res = await fetch('/api/auth/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ username: loginUser, password: loginPass }),
			});
			const data = await res.json();
			if (res.ok && data.token) {
				localStorage.setItem('admin_token', data.token);
				localStorage.setItem('admin_user', data.user);
				adminUser = data.user;
				authenticated = true;
			} else {
				authError = data.error || 'Invalid credentials';
			}
		} catch {
			authError = 'Connection error';
		}
	}

	function logout() {
		localStorage.removeItem('admin_token');
		localStorage.removeItem('admin_user');
		authenticated = false;
		loginUser = '';
		loginPass = '';
	}

	const appName = $derived(instance.app?.name || 'Document Agent');
	const appIcon = $derived(instance.app?.icon || 'hub');

	const nav = [
		{ href: '/', label: 'Tenants', icon: 'hub' },
		{ href: '/monitoring', label: 'Monitoring', icon: 'monitoring' },
		{ href: '/system', label: 'System', icon: 'database' },
		{ href: '/settings', label: 'Config', icon: 'tune' },
	];

	const pageTitle = $derived(
		nav.find(n => n.href === '/' && page.url.pathname === '/'
			? true
			: n.href !== '/' && page.url.pathname.startsWith(n.href)
		)?.label || appName
	);
</script>

{#if checkingAuth}
	<!-- Loading -->
	<div class="flex items-center justify-center h-screen" style="background:#feffd6">
		<div class="text-center">
			<span class="material-symbols-outlined text-4xl animate-pulse" style="color:#383832">hourglass_empty</span>
			<p class="text-[10px] font-black uppercase tracking-widest mt-4" style="color:#65655e">INITIALIZING_SYSTEM</p>
		</div>
	</div>

{:else if authRequired && !authenticated}
	<!-- ═══ LOGIN — Brutalist / Newspaper (matching BCP Command Center) ═══ -->
	<div class="flex flex-col h-screen" style="background:#feffd6">

		<!-- ── Top Header Bar ─────────────────────────────────── -->
		<header class="flex items-center justify-between px-6" style="height:56px;border-bottom:3px solid #383832">
			<span class="px-3 py-1.5 text-lg font-black tracking-tighter uppercase flex items-center gap-2" style="background:#383832;color:#feffd6">
				<img src="/favicon.svg" alt="Scout" style="width:24px;height:24px">
				SCOUT AGENTIC RAG
			</span>
			<span class="text-sm font-bold uppercase tracking-widest" style="color:#383832">SECURE_TERMINAL</span>
		</header>

		<!-- ── Main Content: Left form + Right decoration ───── -->
		<main class="flex-1 flex flex-col lg:flex-row items-center lg:items-stretch overflow-hidden">

			<!-- Left side — form area -->
			<div class="w-full lg:w-1/2 flex flex-col justify-center px-8 md:px-16 lg:px-24 py-12">
				<!-- Authentication badge -->
				<div class="mb-4">
					<span class="tag-label text-xs tracking-wider">AUTHENTICATION_REQUIRED</span>
				</div>

				<!-- Title -->
				<h1 class="text-5xl font-black uppercase tracking-tighter" style="color:#383832">ACCESS_PORTAL</h1>
				<div class="w-full max-w-md mt-2 mb-2" style="border-bottom:3px solid #383832"></div>
				<p class="text-sm font-bold uppercase tracking-wider" style="color:#9d9d91">SCOUT AI — DOCUMENT INTELLIGENCE</p>

				<!-- Form card -->
				<form onsubmit={(e) => { e.preventDefault(); login(); }}
					class="mt-8 p-6 w-full max-w-md space-y-5" style="background:#f6f4e9;border:2px solid #383832">

					{#if authError}
						<div class="p-3 font-bold text-sm uppercase" style="background:#be2d06;color:white;border:2px solid #383832">
							{authError}
						</div>
					{/if}

					<!-- Username -->
					<div>
						<div class="tag-label mb-1">OPERATOR_ID</div>
						<input bind:value={loginUser} type="text" autocomplete="username" placeholder="Enter credentials"
							class="w-full font-bold text-sm" style="padding:12px 16px;background:white;border:2px solid #383832;color:#383832;font-family:'Space Grotesk',sans-serif" />
					</div>

					<!-- Password -->
					<div>
						<div class="tag-label mb-1">ACCESS_KEY</div>
						<div class="relative">
							<input bind:value={loginPass} type={showPass ? 'text' : 'password'} autocomplete="current-password" placeholder="Enter passphrase"
								class="w-full font-bold text-sm" style="padding:12px 16px;padding-right:80px;background:white;border:2px solid #383832;color:#383832;font-family:'Space Grotesk',sans-serif" />
							<button type="button" onclick={() => showPass = !showPass}
								class="absolute right-4 top-1/2 -translate-y-1/2 text-xs font-black uppercase tracking-wider cursor-pointer" style="color:#65655e">
								{showPass ? 'HIDE' : 'SHOW'}
							</button>
						</div>
					</div>

					<!-- Submit -->
					<button type="submit"
						class="w-full font-black text-sm uppercase tracking-wider cursor-pointer active:translate-x-[2px] active:translate-y-[2px] transition-transform"
						style="padding:16px;background:#00fc40;color:#383832;border:2px solid #383832;font-family:'Space Grotesk',sans-serif">
						INITIATE_AUTHENTICATION
					</button>
				</form>

				<!-- Status footer -->
				<div class="mt-8 flex items-center gap-4 text-[10px] font-bold uppercase tracking-widest" style="color:#9d9d91">
					<span class="flex items-center gap-2"><span class="w-2 h-2 inline-block" style="background:#9d9d91"></span> NODE_ACTIVE</span>
					<span>|</span>
					<span>AES-256</span>
					<span>|</span>
					<span>V2.0-STABLE</span>
				</div>
			</div>

			<!-- Right side — giant decorative text (desktop only) -->
			<div class="hidden lg:flex flex-col items-center justify-center w-1/2 select-none overflow-hidden px-8">
				<h2 class="text-8xl xl:text-[9rem] font-black uppercase tracking-tighter leading-[0.85] text-right" style="color:#383832">
					SCOUT<br/>AGENTIC<br/>RAG
				</h2>
				<div class="mt-6 flex items-center gap-4 text-right">
					<span class="text-2xl font-black uppercase tracking-tighter" style="color:#383832">DOCUMENT AGENT</span>
					<span class="text-2xl font-black uppercase tracking-tighter" style="color:#007518">V2.0</span>
				</div>
			</div>
		</main>

		<!-- ── Bottom Footer Bar ──────────────────────────────── -->
		<footer class="flex items-center justify-between px-6" style="height:40px;border-top:3px solid #383832">
			<span class="text-[10px] font-bold uppercase tracking-wider" style="color:#9d9d91">&copy; 2026 SCOUT AI</span>
			<span class="text-[10px] font-bold uppercase tracking-wider" style="color:#9d9d91">SECURE_TERMINAL</span>
		</footer>
	</div>

{:else}
	<!-- ═══ MAIN LAYOUT — Brutalist Header + Content + Footer ═══ -->
	<div class="flex flex-col h-screen" style="background:#feffd6;color:#383832">

		<!-- ── Header (fixed top) ──────────────────────────────── -->
		<header class="fixed top-0 w-full z-50 flex items-center justify-between px-6" style="background:#feffd6;border-bottom:3px solid #383832;height:56px">
			<!-- Brand badge -->
			<div class="flex items-center gap-4">
				<span class="px-2 py-1 text-lg font-black tracking-tighter uppercase flex items-center gap-2" style="background:#383832;color:#feffd6">
					<img src="/favicon.svg" alt="Scout" style="width:24px;height:24px">
					SCOUT AGENTIC RAG
				</span>
			</div>

			<!-- Nav -->
			<nav class="hidden md:flex items-center gap-0">
				{#each nav as item}
					{@const active = page.url.pathname === item.href || (item.href !== '/' && page.url.pathname.startsWith(item.href))}
					<a href={item.href}
						class="flex items-center gap-2 px-3 py-1.5 text-sm font-bold uppercase tracking-tight cursor-pointer transition-colors"
						style={active ? 'background:#383832;color:#feffd6' : 'color:#383832'}
						onmouseenter={(e) => { if (!active) { e.currentTarget.style.background='#007518'; e.currentTarget.style.color='white'; }}}
						onmouseleave={(e) => { if (!active) { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='#383832'; }}}>
						<span class="material-symbols-outlined text-sm" style={active ? "font-variation-settings:'FILL' 1;color:#00fc40" : ''}>{item.icon}</span>
						{item.label}
					</a>
				{/each}
			</nav>

			<!-- User + Logout -->
			<div class="flex items-center gap-3">
				<div class="w-9 h-9 flex items-center justify-center font-bold text-sm" style="background:#9d4867;color:white;border:2px solid #383832">
					{adminUser ? adminUser[0].toUpperCase() : 'A'}
				</div>
				<button onclick={logout} class="flex items-center gap-1 px-2 py-1 text-[10px] font-black uppercase tracking-wider cursor-pointer transition-colors" style="color:#9d4867;border:1px solid #9d4867"
					onmouseenter={(e) => { e.currentTarget.style.background='#9d4867'; e.currentTarget.style.color='white'; }}
					onmouseleave={(e) => { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='#9d4867'; }}>
					<span class="material-symbols-outlined text-sm">logout</span>
					LOGOUT
				</button>
			</div>
		</header>

		<!-- ── Main content area ───────────────────────────────── -->
		<main class="flex-1 overflow-y-auto pt-[72px] pb-[56px] px-6" style="max-width:1920px;margin:0 auto;width:100%">
			{@render children()}
		</main>

		<!-- ── Footer (fixed bottom) ──────────────────────────── -->
		<footer class="fixed bottom-0 left-0 w-full z-50 flex items-stretch overflow-hidden" style="background:#feffd6;border-top:3px solid #383832;height:40px">
			<!-- Green status segment -->
			<div class="flex items-center px-4" style="background:#007518;color:white;border-right:2px solid #383832">
				<span class="material-symbols-outlined text-sm mr-2">check_circle</span>
				<span class="font-mono text-[11px] font-bold uppercase tracking-widest">SYSTEM_ACTIVE</span>
			</div>
			<!-- Page title -->
			<div class="flex items-center px-4" style="border-right:2px solid #383832">
				<span class="font-mono text-[11px] font-bold uppercase tracking-wider" style="color:#383832">{pageTitle}</span>
			</div>
			<!-- Spacer -->
			<div class="flex-1"></div>
			<!-- LIVE_FEED badge -->
			<div class="flex items-center px-4" style="border-left:2px solid #383832">
				<span class="px-2 py-0.5 text-[10px] font-bold uppercase animate-pulse" style="background:#9d4867;color:white;border:1px solid #383832">LIVE_FEED</span>
			</div>
		</footer>
	</div>
{/if}
