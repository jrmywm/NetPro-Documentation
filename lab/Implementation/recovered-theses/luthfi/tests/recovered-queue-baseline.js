// Isolated harness: recovered services/models are unchanged; only DB binding is injected.
const path=require('path'),fs=require('fs'),crypto=require('crypto');
const {Sequelize}=require('sequelize');
const src=path.resolve(process.argv[2]);
const database=process.env.BASELINE_DATABASE;
if(!/^netpro_original_baseline_[0-9]+$/.test(database))throw Error('Expected isolated database');
const config={host:'127.0.0.1',dialect:'postgres',logging:false};
const admin=new Sequelize('postgres','postgres',process.env.BASELINE_PG_PASSWORD,config);
let sql;
(async()=>{
 await admin.query('CREATE DATABASE "'+database+'"');await admin.close();
 sql=new Sequelize(database,'postgres',process.env.BASELINE_PG_PASSWORD,config);
 const db={Sequelize,sequelize:sql};
 for(const [key,file] of [['blacklist','blacklist'],['uploadJob','uploadJob'],['failedUpload','failedUpload']])db[key]=require(path.join(src,'app/models/'+file+'.model.js'))(sql,Sequelize);
 await sql.sync();
 const configFile=require.resolve(path.join(src,'app/config/db.config.js'));
 require.cache[configFile]={id:configFile,filename:configFile,loaded:true,exports:db};
 const adapted=process.env.BASELINE_ADAPTED==='1';
 const Service=require(path.join(src,adapted?'app/services/bounded-upload.service.js':'app/services/job.service.js'));
 const queue=require(path.join(src,'app/services/queue.service.js'));
 const service=new Service();
 const events=[];global.io={emit:(name,data)=>events.push({name,progress:data.progress,status:data.status})};
 const result=[];
 for(const n of [10000,100000]){
  const file=path.join(src,'fixture-'+n+'.csv');let data='domain,name,category,reason,hit_count\n';
  for(let i=0;i<n;i++)data+=`baseline-${n}-${i}.example,baseline,other,,0\n`;
  fs.writeFileSync(file,data);
  const hash=crypto.createHash('sha256').update(data).digest('hex');
  const job=await db.uploadJob.create({filename:path.basename(file),status:'queued'});
  const before=await db.blacklist.count(),start=process.hrtime.bigint();
  if(adapted)await service.process(file,job.id);
  else await queue.addToQueue({filePath:file,jobId:job.id,filename:path.basename(file),processFileInChunks:service.processFileInChunks.bind(service)});
  const seconds=Number(process.hrtime.bigint()-start)/1e9;
  const after=await db.blacklist.count();await job.reload();
  if(after-before!==n||job.status!=='completed')throw Error('Wrong baseline count/status');
  result.push({rows:n,seconds,rowsPerSecond:n/seconds,sha256:hash,inserted:after-before,job:job.toJSON(),progressEvents:events.length});
 }
 fs.writeFileSync(path.join(src,'RESULTS.json'),JSON.stringify({scope:adapted?'adapted bounded processing core, 1000-row batches; direct worker invocation, excludes persistent queue scheduling and publication':'actual recovered better-queue and unchanged 10000-row service; isolated PostgreSQL; progress emit collector only, not browser/Socket.IO acceptance',database,result},null,2));
 await sql.close();console.log('BASELINE_PASS');process.exit(0);
})().catch(async e=>{console.error(e);if(sql)await sql.close();process.exit(1)});
