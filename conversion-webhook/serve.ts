import fs from "fs"
import { createServer } from "https"
import express from "express"
import morgan from "morgan"
import bodyparser from "body-parser"


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
      convertedObjects: request.objects.map((o) => {
        console.log("Converting: " + JSON.stringify(o))
        if (o.apiVersion == "wordpress.epfl.ch/v1") {
          o.apiVersion = "wordpress.epfl.ch/v2";
          o.spec.wordpress.plugins = Object.fromEntries(o.spec.wordpress.plugins.map((k) => [k, {}]));
          console.log("Converted: " + JSON.stringify(o))
        }
        return o
      }),
    }
  });
})

createServer({ key: fs.readFileSync("server.key"), cert: fs.readFileSync("server.pem")}, app).listen(6443);
