#!/bin/bash
# K-Drama Bot - Quick Activation Script
# Usage: ./activate.sh

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   K-DRAMA BOT - QUICK ACTIVATION                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found!${NC}"
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
source venv/bin/activate

echo -e "${GREEN}✅ Virtual environment activated${NC}"
echo -e "${BLUE}Environment Info:${NC}"
echo "  Python: $(python --version)"
echo "  Pip: $(pip --version | cut -d' ' -f2)"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found!${NC}"
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}📋 Creating .env from template...${NC}"
        cp .env.example .env
        echo -e "${YELLOW}📝 Please edit .env with your credentials:${NC}"
        echo -e "${YELLOW}   nano .env${NC}"
    fi
else
    echo -e "${GREEN}✅ .env file found${NC}"
fi

echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Edit .env file with your credentials:"
echo -e "     ${YELLOW}nano .env${NC}"
echo ""
echo "  2. Run the bot:"
echo -e "     ${YELLOW}python -m bot.main${NC}"
echo ""
echo "  3. Open Telegram and test your bot!"
echo ""
echo -e "${GREEN}Ready to go! 🚀${NC}"
