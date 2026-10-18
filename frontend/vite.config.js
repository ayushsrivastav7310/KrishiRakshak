import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
// Vercel services route requests at the shared domain. The localhost proxy is
// only needed when running Vite directly alongside the local Python server.
export default defineConfig({root:fileURLToPath(new URL('.',import.meta.url)),plugins:[react(),tailwindcss()],server:{strictPort:true,...(!process.env.VERCEL&&{proxy:{'/api':'http://127.0.0.1:8000','/voice':'http://127.0.0.1:8000'}})}});


