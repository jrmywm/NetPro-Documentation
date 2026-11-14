module.exports = (sequelize, Sequelize) => {
  const FailedUpload = sequelize.define("failed_upload", {
    id: {
      type: Sequelize.INTEGER,
      primaryKey: true,
      autoIncrement: true
    },
    job_id: {
      type: Sequelize.INTEGER,
      allowNull: false,
      references: {
        model: 'upload_jobs',
        key: 'id'
      }
    },
    row_number: {
      type: Sequelize.INTEGER,
      allowNull: false,
      comment: 'The row number in the original CSV file'
    },
    name: {
      type: Sequelize.STRING,
      allowNull: true
    },
    domain: {
      type: Sequelize.STRING,
      allowNull: false
    },
    reason: {
      type: Sequelize.TEXT,
      allowNull: true
    },
    category: {
      type: Sequelize.STRING,
      allowNull: true
    },
    hit_count: {
      type: Sequelize.INTEGER,
      allowNull: true
    },
    error_message: {
      type: Sequelize.TEXT,
      allowNull: false,
      comment: 'The reason why this record failed to upload'
    },
    original_data: {
      type: Sequelize.TEXT,
      allowNull: true,
      comment: 'The original data from CSV in JSON format'
    }
  });

  return FailedUpload;
}; 