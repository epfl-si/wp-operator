"use strict";
const fs = require('fs');
const { exec } = require('child_process');

const namespace = "wordpress-test";
const patchFile = 'scripts/patch.sh';

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

function write(filePath, content) {
	fs.appendFile(filePath, content, (err) => {
		if (err) throw err;
	});
}

function makeFileExecutable() {
	fs.chmod(patchFile, 0o755, (err) => {
		if (err) throw err;
		console.log('Permissions changed successfully!');
	});

}

const run = async () => {
	const command = `kubectl get wps -n ${namespace} -o json | jq '[.items[] | {NAME: .metadata.name, UID: .metadata.uid}]'`;
	const wps = await execKubectl(command);
	for (const site of wps) {
		write(patchFile,`kubectl patch databases wp-db-${site.NAME} -n ${namespace} --type='merge' -p '{"metadata":{"ownerReferences":[{"apiVersion":"wordpress.epfl.ch/v1","kind":"WordpressSite","name":"${site.NAME}","uid":"${site.UID}"}]}}' \n`)
		write(patchFile,`kubectl patch umdb wp-db-user-${site.NAME} -n ${namespace} --type='merge' -p '{"metadata":{"ownerReferences":[{"apiVersion":"wordpress.epfl.ch/v1","kind":"WordpressSite","name":"${site.NAME}","uid":"${site.UID}"}]}}' \n`)
		write(patchFile,`kubectl patch grant wp-db-grant-${site.NAME} -n ${namespace} --type='merge' -p '{"metadata":{"ownerReferences":[{"apiVersion":"wordpress.epfl.ch/v1","kind":"WordpressSite","name":"${site.NAME}","uid":"${site.UID}"}]}}' \n`)
		write(patchFile,`kubectl patch secret wp-db-password-${site.NAME} -n ${namespace} --type='merge' -p '{"metadata":{"ownerReferences":[{"apiVersion":"wordpress.epfl.ch/v1","kind":"WordpressSite","name":"${site.NAME}","uid":"${site.UID}"}]}}' \n`)
		write(patchFile,`kubectl patch ingress ${site.NAME} -n ${namespace} --type='merge' -p '{"metadata":{"ownerReferences":[{"apiVersion":"wordpress.epfl.ch/v1","kind":"WordpressSite","name":"${site.NAME}","uid":"${site.UID}"}]}}' \n`)
		write(patchFile,`kubectl patch route wp-route-${site.NAME} -n ${namespace} --type='merge' -p '{"metadata":{"ownerReferences":[{"apiVersion":"wordpress.epfl.ch/v1","kind":"WordpressSite","name":"${site.NAME}","uid":"${site.UID}"}]}}' \n`)
	}
	makeFileExecutable();
}

run();
