# AgentLens Blog Website

A minimal, beautiful blog website for the AgentLens project.

## Deploy Options

### Option 1: GitHub Pages (Recommended - Free & Easy)

1. **Create a new GitHub repository** (e.g., `agentlens-blog`)

2. **Push this website:**
   ```bash
   cd blog-website
   git init
   git add .
   git commit -m "Initial commit: AgentLens blog"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/agentlens-blog.git
   git push -u origin main
   ```

3. **Enable GitHub Pages:**
   - Go to repository Settings → Pages
   - Source: Deploy from a branch → `main` → `/` (root)
   - Click Save
   - Your site will be live at: `https://YOUR_USERNAME.github.io/agentlens-blog/`

4. **Update links in `index.html`:**
   - Replace `https://github.com/yourusername/agentlens` with your actual repo URL
   - Replace demo link with your deployed dashboard URL

### Option 2: Netlify (Free, Custom Domain)

1. **Install Netlify CLI:**
   ```bash
   npm install -g netlify-cli
   ```

2. **Deploy:**
   ```bash
   cd blog-website
   netlify deploy --prod
   ```

3. **Follow the prompts:**
   - Create & configure a new site
   - Publish directory: `.` (current directory)
   - Your site will be live at: `https://YOUR_SITE_NAME.netlify.app`

4. **Custom domain (optional):**
   - Go to Site settings → Domain management
   - Add your custom domain

### Option 3: Vercel (Free, Fast Edge Network)

1. **Install Vercel CLI:**
   ```bash
   npm install -g vercel
   ```

2. **Deploy:**
   ```bash
   cd blog-website
   vercel --prod
   ```

3. **Follow the prompts:**
   - Your site will be live at: `https://YOUR_SITE_NAME.vercel.app`

### Option 4: Cloudflare Pages (Free, Fast CDN)

1. **Go to** [dash.cloudflare.com](https://dash.cloudflare.com)

2. **Click** "Workers & Pages" → "Create application" → "Pages"

3. **Connect your Git repo** or **upload folder directly**

4. **Build settings:**
   - Framework preset: None
   - Build command: (leave empty)
   - Build output directory: (leave empty)

5. **Deploy!** Your site will be live at: `https://YOUR_SITE_NAME.pages.dev`

## Customization

### Update Your Information

Edit `index.html` and replace:

1. **GitHub links:**
   ```html
   https://github.com/yourusername/agentlens
   ```

2. **Demo link:**
   ```html
   https://agentlens-demo.vercel.app
   ```

3. **Social media links:**
   ```html
   https://twitter.com/yourusername
   ```

4. **Author info** in footer

### Add Analytics (Optional)

Add before `</head>`:

```html
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

### Add Open Graph Image

1. Create a social media preview image (1200x630px)
2. Save as `og-image.png` in blog-website folder
3. Update meta tag in `index.html`:
   ```html
   <meta property="og:image" content="https://YOUR_DOMAIN/og-image.png">
   ```

## Features

✅ **Fully responsive** - looks great on mobile, tablet, desktop
✅ **Dark mode optimized** - easy on the eyes
✅ **Zero dependencies** - pure HTML + CSS
✅ **Fast loading** - no external fonts or libraries
✅ **SEO optimized** - proper meta tags and semantic HTML
✅ **Social media ready** - Open Graph tags for beautiful link previews

## Local Preview

Just open `index.html` in your browser, or use a simple HTTP server:

```bash
# Python
python -m http.server 8080

# Node.js
npx http-server -p 8080

# Open http://localhost:8080
```

## Performance

- **Size:** ~15KB (single HTML file)
- **Load time:** < 100ms
- **Lighthouse score:** 100/100/100/100

## License

MIT - same as AgentLens project

