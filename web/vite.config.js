import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget =
    process.env.VITE_API_PROXY_TARGET ||
    process.env.VITE_API_ORIGIN ||
    env.VITE_API_PROXY_TARGET ||
    env.VITE_API_ORIGIN ||
    'http://127.0.0.1:8147'
  const apiProxy = {
    '/api': {
      target: apiProxyTarget,
      changeOrigin: true,
    },
  }

  return {
    plugins: [
      vue(),
      AutoImport({
        resolvers: [ElementPlusResolver()],
      }),
      Components({
        resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      }),
    ],
    server: {
      proxy: apiProxy,
    },
    preview: {
      proxy: apiProxy,
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            vue: ['vue', 'vue-router'],
            axios: ['axios'],
          },
        },
      },
    },
  }
})
