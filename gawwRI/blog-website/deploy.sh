#!/bin/bash

# AgentLens Blog Deployment Script
# Choose your deployment platform and follow the instructions

echo "🔍 AgentLens Blog Deployment"
echo "=============================="
echo ""
echo "Choose your deployment platform:"
echo "1) GitHub Pages (Free, easiest)"
echo "2) Netlify (Free, custom domain)"
echo "3) Vercel (Free, fast edge network)"
echo "4) Just preview locally"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
  1)
    echo ""
    echo "📦 Deploying to GitHub Pages..."
    echo ""
    echo "Follow these steps:"
    echo "1. Create a new repository on GitHub (e.g., 'agentlens-blog')"
    echo "2. Run these commands:"
    echo ""
    echo "   git init"
    echo "   git add ."
    echo "   git commit -m 'Initial commit: AgentLens blog'"
    echo "   git branch -M main"
    echo "   git remote add origin https://github.com/YOUR_USERNAME/agentlens-blog.git"
    echo "   git push -u origin main"
    echo ""
    echo "3. Go to Settings → Pages"
    echo "4. Source: Deploy from a branch → main → / (root)"
    echo "5. Click Save"
    echo ""
    echo "Your site will be live at: https://YOUR_USERNAME.github.io/agentlens-blog/"
    ;;
    
  2)
    echo ""
    echo "📦 Deploying to Netlify..."
    echo ""
    
    # Check if netlify-cli is installed
    if ! command -v netlify &> /dev/null; then
        echo "Installing Netlify CLI..."
        npm install -g netlify-cli
    fi
    
    echo "Deploying..."
    netlify deploy --prod
    ;;
    
  3)
    echo ""
    echo "📦 Deploying to Vercel..."
    echo ""
    
    # Check if vercel-cli is installed
    if ! command -v vercel &> /dev/null; then
        echo "Installing Vercel CLI..."
        npm install -g vercel
    fi
    
    echo "Deploying..."
    vercel --prod
    ;;
    
  4)
    echo ""
    echo "🌐 Starting local preview..."
    echo ""
    
    # Check for available HTTP server
    if command -v python3 &> /dev/null; then
        echo "Opening http://localhost:8080"
        python3 -m http.server 8080
    elif command -v python &> /dev/null; then
        echo "Opening http://localhost:8080"
        python -m http.server 8080
    elif command -v npx &> /dev/null; then
        echo "Opening http://localhost:8080"
        npx http-server -p 8080
    else
        echo "Please install Python or Node.js to run a local server"
        echo "Or just open index.html directly in your browser!"
    fi
    ;;
    
  *)
    echo "Invalid choice. Please run again and choose 1-4."
    exit 1
    ;;
esac

