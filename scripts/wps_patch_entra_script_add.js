"use strict";
const { promises: fs } = require("fs");
const { exec } = require('child_process');

const namespace = "svc0041p-wordpress";
const patchFile = 'patch_entra_prod_inside_add.sh';

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
			{ "op": "add", "path": "/spec/wordpress/plugins/daggerhart-openid-connect-generic", "value": {} }
		  ]'\n` );
		}
	}
	await makeFileExecutable();
}

run();
