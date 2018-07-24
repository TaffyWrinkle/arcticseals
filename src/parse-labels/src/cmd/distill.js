let fs = require('fs');
let path = require('path');
let csvUtil = require('../util/csv');
let imageUtil = require('../util/image');
let fileUtil = require('../util/file');

module.exports.registerCommand = (program) => {
    program
        .command('distill <file>')
        .option('-i, --imgdirs <dirs>', 'Comma-separated list of file paths containing images')
        .option('-o, --outfile <file>', 'Output CSV file (in normalized format)')
        .description('Distill raw CSV file (only include hotspots w/ images)')
        .action((file, command) => {
            const filter = (record) => {
                // Don't care about duplicates, evidence of seal, etc.
                return record.hotspot_type === 'Animal' || record.hotspot_type === 'Anomaly'
            };
            let records = csvUtil.getCsvRecordsFromRawCsv(file, [filter]); 
            let imageMap = imageUtil.getImageMap(command.imgdirs.split(','), command.imgtype);
            let distilledRecords = [];
            let recordsExcluded = 0;
            let recordsIncluded = 0;
            let recordsIncludedWithoutColor = 0;
            let recordsIncludedNotInMaster = 0;
            for (let record of records) {
                if (imageMap.has(record.filt_thermal16)) {
                    if (!imageMap.has(record.filt_color)) {
                        record.filt_color = '',
                        record.thumb_left = 0,
                        record.thumb_top = 0,
                        record.thumb_right = 0,
                        record.thumb_bottom = 0
                        recordsIncludedWithoutColor++;
                    }
                    distilledRecords.push(record);
                    recordsIncluded++;
                } else {
                    recordsExcluded++;
                }
            }
            let writer = fs.createWriteStream(command.outfile);
            csvUtil.writeCsvHeader(writer);
            for (let distilledRecord of distilledRecords) {
                csvUtil.writeCsvRecord(writer, distilledRecord);
            }
            console.log(`${recordsIncluded} records included (${recordsIncludedWithoutColor} without color), ${recordsExcluded} records excluded.`);
            // TODO.NEXTSTEP merge with master (only add net new) - careful to check validation set too
            // TODO.NEXTSTEP include dataset name in extra column
    });
}