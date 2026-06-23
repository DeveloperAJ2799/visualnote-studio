import { renderMediaOnLambda } from "@remotion/lambda";
import * as dotenv from "dotenv";

dotenv.config();

const functionName = process.env.REMOTION_FUNCTION_NAME!;
const region = process.env.AWS_REGION!;

async function main() {
  const { renderId, bucketName } = await renderMediaOnLambda({
    functionName,
    region,
    composition: "VideoComposition",
    inputProps: {
      manifest_url: process.env.MANIFEST_URL!,
    },
    outName: "output.mp4",
    codec: "h264",
  });
  console.log(`Render started: ${renderId} in bucket ${bucketName}`);
}

main();