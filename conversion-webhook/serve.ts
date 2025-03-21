import fs from "fs"
import { createServer } from "https"
import express from "express"
import morgan from "morgan"
import bodyparser from "body-parser"
import debug_ from "debug";

const debug = debug_("wordpresssite-conversion-webhook");

function convertWordpressSite (wp) {
  debug("Converting: " + JSON.stringify(wp))
  if (wp.apiVersion == "wordpress.epfl.ch/v1") {
    wp.apiVersion = "wordpress.epfl.ch/v2";
    wp.spec.wordpress.plugins = Object.fromEntries(
      wp.spec.wordpress.plugins.map((k) => [k, {}]));
    debug("Converted: " + JSON.stringify(wp))
  }
  return wp
}

const app = express();
app.use(morgan('combined'));
app.use(bodyparser.json());

app.use("/", function (req, res) {
  const request = req.body.request;
  res.json({   // https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definition-versioning/
    "apiVersion": "apiextensions.k8s.io/v1",
    "kind": "ConversionReview",
    response: {
      "result": {
        "status": "Success"
      },
      uid: request.uid,
      convertedObjects: request.objects.map(convertWordpressSite),
    }
  });
})

createServer({ key: fs.readFileSync("server.key"), cert: fs.readFileSync("server.pem")}, app).listen(6443);
