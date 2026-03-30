# Price Alert Bot - Full Stack Application

Your Telegram bot has been extended into a full-stack application with web and mobile interfaces.

## Project Structure

```
signals bot/
├── backend/                 # FastAPI backend
│   ├── main.py            # API server with WebSocket support
│   └── requirements.txt
├── web-app/               # Next.js web application
│   ├── src/app/
│   │   ├── page.tsx      # Dashboard
│   │   └── globals.css
│   ├── package.json
│   └── tsconfig.json
├── mobile-app/            # React Native mobile app
│   ├── App.tsx
│   ├── screens/
│   │   ├── DashboardScreen.tsx
│   │   ├── AddAssetScreen.tsx
│   │   └── AlertsScreen.tsx
│   ├── package.json
│   └── app.json
└── (original bot files)    # Your existing Telegram bot
```

## Running the Application

### 1. Start the Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The API runs on `http://localhost:8000`

**API Endpoints:**
- `GET /assets` - List tracked assets
- `POST /assets` - Add an asset
- `DELETE /assets/{name}` - Remove an asset
- `GET /assets/available` - List available assets
- `WS /ws` - WebSocket for real-time updates

### 2. Start the Web App

```bash
cd web-app
npm install
npm run dev
```

Open `http://localhost:3000`

### 3. Start the Mobile App

```bash
cd mobile-app
npm install
npx expo start
```

Scan the QR code with Expo Go app.

## Features

| Feature | Web | Mobile |
|---------|-----|--------|
| View tracked assets | ✅ | ✅ |
| Add/remove assets | ✅ | ✅ |
| Real-time prices | ✅ | ✅ |
| Alert history | ✅ | ✅ |
| Dark theme | ✅ | ✅ |
| Push notifications | - | (Configure FCM) |

## Configuration

Update `YOUR_SERVER_IP:8000` in mobile-app/screens/ with your backend server address.

For production, use environment variables:
- `NEXT_PUBLIC_API_URL` for web app
- Store backend URL in mobile app config
