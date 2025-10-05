const { google } = require('googleapis');
const readline = require('readline');
require('dotenv').config();

// OAuth2 client setup
const CLIENT_ID = process.env.CLIENT_ID;
const CLIENT_SECRET = process.env.CLIENT_SECRET;
const REDIRECT_URI = 'https://developers.google.com/oauthplayground';

const oauth2Client = new google.auth.OAuth2(
  CLIENT_ID,
  CLIENT_SECRET,
  REDIRECT_URI
);

// Generate the authorization URL
const authUrl = oauth2Client.generateAuthUrl({
access_type: 'offline',
  scope: ['https://www.googleapis.com/auth/gmail.send'],
  prompt: 'consent'  // Force to get a new refresh token
});

console.log('Authorize this app by visiting this URL:', authUrl);

// Create readline interface for user input
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

// Get the authorization code from the user
rl.question('Enter the code from that page here: ', (code) => {
  rl.close();
  
  // Exchange the authorization code for tokens
  oauth2Client.getToken(code, (err, tokens) => {
    if (err) {
      console.error('Error getting tokens:', err);
      return;
    }
    
    console.log('Refresh Token:', tokens.refresh_token);
    console.log('Access Token:', tokens.access_token);
    
    console.log('\nAdd this refresh token to your .env file:');
    console.log(`REFRESH_TOKEN=${tokens.refresh_token}`);
  });
}); 