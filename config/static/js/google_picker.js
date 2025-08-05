// Based on https://developers.google.com/drive/picker/guides/overview#hiworld

let tokenClient;
let accessToken = googlePickerConfig.accessToken || null;
let pickerInited = false;
let gisInited = false;

// Use the API Loader script to load google.picker
function onApiLoad() {
  gapi.load("picker", onPickerApiLoad);
}

function onPickerApiLoad() {
  pickerInited = true;
  maybeAddPickerButton();
}

function gisLoaded() {
  tokenClient = google.accounts.oauth2.initTokenClient({
    client_id: googlePickerConfig.clientId,
    scope: googlePickerConfig.scopes,
    callback: "", // defined later
  });
  gisInited = true;
  maybeAddPickerButton();
}

function maybeAddPickerButton() {
  if (pickerInited && gisInited && googlePickerConfig.initCallback) {
    googlePickerConfig.initCallback();
  }
}

// Create and render a Google Picker object for selecting from Drive.
function createPicker() {
  const showPicker = () => {
    const picker = new google.picker.PickerBuilder()
      .addView(
        new google.picker.DocsView(google.picker.ViewId.SPREADSHEETS)
          .setMode(google.picker.DocsViewMode.LIST)
          // Exclude Excel files stored in Google Drive (https://drive.google.com/file/... URLs)
          // which gspread won't be able to open (raises gspread.exceptions.NoValidUrlKeyFound)
          .setMimeTypes("application/vnd.google-apps.spreadsheet")
          .setFileIds(googlePickerConfig.preselectedFileId || ""),
      )
      .enableFeature(google.picker.Feature.NAV_HIDDEN)
      .setOAuthToken(accessToken)
      .setDeveloperKey(googlePickerConfig.apiKey)
      .setCallback(pickerCallback)
      .setAppId(googlePickerConfig.appId)
      .build();
    picker.setVisible(true);
  };

  // Request an access token.
  tokenClient.callback = async (response) => {
    if (response.error !== undefined) {
      throw response;
    }
    accessToken = response.access_token;
    showPicker();
  };

  if (accessToken) {
    // Skip display of account chooser and consent dialog for an existing session.
    tokenClient.requestAccessToken({ prompt: "" });
  } else {
    // Prompt the user to select a Google Account and ask for consent to share their data
    // when establishing a new session.
    tokenClient.requestAccessToken({ prompt: "consent" });
  }
}

// Callback called when the user selects a spreadsheet in the Google Picker dialog
function pickerCallback(data) {
  if (data[google.picker.Response.ACTION] == google.picker.Action.PICKED) {
    if (googlePickerConfig.filePickedCallback) {
      googlePickerConfig.filePickedCallback();
    } else {
      const doc = data[google.picker.Response.DOCUMENTS][0];
      url = doc[google.picker.Document.URL];
      document.querySelector(googlePickerConfig.urlInputSelector).value = url;
      document.querySelector(googlePickerConfig.userInputSelector).value =
        googlePickerConfig.user;
    }
  }
}
