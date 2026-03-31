"use strict";
const { promises: fs } = require("fs");
const { exec } = require('child_process');

const namespace = "svc0041p-wordpress";
const patchFile = 'patch_entra_prod_inside_remove.sh';

async function execKubectl(command) {
	return new Promise((resolve, reject) => {
		exec(command, (error, stdout, stderr) => {
			if (error) {
				reject(`Error executing command: ${error.message}`);
				return;
			}
			if (stderr) {
				reject(`Error output: ${stderr}`);
				return;
			}
			resolve(JSON.parse(stdout));
		});
	});
}

async function write(content) {
	await fs.appendFile(patchFile, content);
}

async function makeFileExecutable() {
	await fs.chmod(patchFile, 0o755);
}

const run = async () => {
	const command = `kubectl get wps -n ${namespace} -o json | jq '[.items[] | {NAME: .metadata.name, UID: .metadata.uid}]'`;
	const wps = await execKubectl(command);
	for (const site of wps) {
		if (site.NAME.indexOf("inside") !== -1) {
			await write( `kubectl patch wp ${site.NAME} -n ${namespace} --type='json' -p '[
			{ "op": "remove", "path": "/spec/wordpress/plugins/daggerhart-openid-connect-generic" }
		  ]'\n` );
			await write( `kubectl patch wp ${site.NAME} -n ${namespace} --type='json' -p '[
			{ "op": "remove", "path": "/spec/wordpress/plugins/openid-connect-generic" }
		  ]'\n` );
			await write( `kubectl patch wp ${site.NAME} -n ${namespace} --type='json' -p '[
			{ "op": "remove", "path": "/spec/wordpress/plugins/wp-epfl-openid-configuration" }
		  ]'\n` );
			await write( `kubectl patch wp ${site.NAME} -n ${namespace} --type='json' -p '[
			{ "op": "remove", "path": "/spec/wordpress/plugins/tequila" }
		  ]'\n` );
		}
		// await write(`kubectl patch wp ${site.NAME} -n ${namespace} --type='merge' -p '{"spec":{"wordpress": {"plugins": {
			// "openid-connect-generic": {"wp_options": [
			// 	{
			// 		"name": "openid_connect_generic_settings",
			// 		"value": {
			// 		  "login_type": "auto",
			// 		  "client_id": "${clientID}",
			// 		  "scope": "openid profile email ${clientID}/.default",
			// 		  "endpoint_login": "https://login.microsoftonline.com/f6c2556a-c4fb-4ab1-a2c7-9e220df11c43/oauth2/v2.0/authorize",
			// 		  "endpoint_token": "https://login.microsoftonline.com/f6c2556a-c4fb-4ab1-a2c7-9e220df11c43/oauth2/v2.0/token",
			// 		  "identity_key": "uniqueid",
			// 		  "nickname_key": "gaspar",
			// 		  "email_format": "{email}",
			// 		  "enforce_privacy": 0,
			// 		  "http_request_timeout": "15",
			// 		  "link_existing_users": 1,
			// 		  "endpoint_userinfo": "https://api.epfl.ch/v1/oidc/userinfo"
			// 		}
			//   }
			// ]}, "wp-epfl-openid-configuration": {}, "accred.entra": {}
			// }}}}' \n` );
	}
	await makeFileExecutable();
}

run();
